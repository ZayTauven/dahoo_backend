from django.db.models import Count, Max, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.http import pdf_response
from inspections.models import Inspection, InspectionItem, InspectionPhoto
from inspections.photos import MAX_PHOTOS, photo_id, prepare
from inspections.report import inspection_report, share_inspection
from inspections.services import create_inspection, ensure_draft, reopen_inspection, sign_inspection
from leases.models import LeaseContract
from organizations.scoping import OrganizationScopedMixin
from payments.api.serializers import ShareLinkSerializer

from .serializers import (
    InspectionCreateSerializer,
    InspectionItemSerializer,
    InspectionPhotoSerializer,
    InspectionPhotoUploadSerializer,
    InspectionSerializer,
    InspectionSignSerializer,
    InspectionSummarySerializer,
)

INSPECTIONS = Inspection.objects.select_related(
    "organization", "lease__tenant", "lease__unit__building__property"
).prefetch_related("items__reference", "photos")


class LeaseInspectionsAPIView(OrganizationScopedMixin, APIView):
    """États des lieux d'un bail ; en créer un prépare la liste des pièces à regarder."""

    capability_resource = "inspection"

    def get_lease(self, pk):
        return get_object_or_404(LeaseContract.objects.select_related("unit"), pk=pk, organization=self.organization)

    @extend_schema(responses=InspectionSummarySerializer(many=True))
    def get(self, request, pk):
        rows = self.get_lease(pk).inspections.annotate(
            items_count=Count("items", distinct=True),
            done_count=Count("items", filter=~Q(items__condition=""), distinct=True),
            photos_count=Count("photos", distinct=True),
        )
        return Response(InspectionSummarySerializer(rows, many=True).data)

    @extend_schema(request=InspectionCreateSerializer, responses={201: InspectionSerializer})
    def post(self, request, pk):
        serializer = InspectionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inspection = create_inspection(self.get_lease(pk), user=request.user, **serializer.validated_data)
        return Response(InspectionSerializer(INSPECTIONS.get(pk=inspection.pk)).data, status=status.HTTP_201_CREATED)


class InspectionMixin(OrganizationScopedMixin):
    def get_inspection(self, pk):
        return get_object_or_404(INSPECTIONS, pk=pk, organization=self.organization)


class InspectionDetailAPIView(InspectionMixin, generics.RetrieveUpdateDestroyAPIView):
    capability_resource = "inspection"
    serializer_class = InspectionSerializer
    queryset = INSPECTIONS
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def perform_update(self, serializer):
        ensure_draft(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        ensure_draft(instance)
        # Les photos d'abord, une à une : chaque suppression retire aussi son fichier.
        for photo in instance.photos.all():
            photo.delete()
        instance.delete()


class InspectionItemCreateAPIView(InspectionMixin, APIView):
    required_capability = "inspection.update"

    @extend_schema(request=InspectionItemSerializer, responses={201: InspectionItemSerializer})
    def post(self, request, pk):
        inspection = self.get_inspection(pk)
        ensure_draft(inspection)
        serializer = InspectionItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room = serializer.validated_data["room"]
        # À la suite de sa pièce, pour ne pas la couper en deux.
        last = inspection.items.filter(room=room).aggregate(last=Max("position"))["last"]
        if last is None:
            last = inspection.items.aggregate(last=Max("position"))["last"] or 0
        else:
            for item in inspection.items.filter(position__gt=last):
                item.position += 1
                item.save(update_fields=["position"])
        item = serializer.save(inspection=inspection, position=last + 1)
        return Response(InspectionItemSerializer(item).data, status=status.HTTP_201_CREATED)


class InspectionItemDetailAPIView(OrganizationScopedMixin, generics.UpdateAPIView, generics.DestroyAPIView):
    required_capability = "inspection.update"
    organization_lookup = "inspection__organization"
    queryset = InspectionItem.objects.select_related("inspection", "reference")
    serializer_class = InspectionItemSerializer
    http_method_names = ["patch", "delete", "head", "options"]

    def perform_update(self, serializer):
        ensure_draft(serializer.instance.inspection)
        serializer.save()

    def perform_destroy(self, instance):
        ensure_draft(instance.inspection)
        for photo in instance.photos.all():
            photo.delete()
        instance.delete()


class InspectionPhotoCreateAPIView(InspectionMixin, APIView):
    required_capability = "inspection.update"
    parser_classes = [MultiPartParser]

    @extend_schema(request=InspectionPhotoUploadSerializer, responses={201: InspectionPhotoSerializer})
    def post(self, request, pk):
        inspection = self.get_inspection(pk)
        ensure_draft(inspection)
        serializer = InspectionPhotoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if inspection.photos.count() >= MAX_PHOTOS:
            raise ValidationError({"image": f"{MAX_PHOTOS} photos au plus par état des lieux."})
        item = None
        if serializer.validated_data.get("item"):
            item = get_object_or_404(inspection.items, pk=serializer.validated_data["item"])
        try:
            image = prepare(serializer.validated_data["image"])
        except ValidationError as error:
            raise ValidationError({"image": error.detail})
        photo = InspectionPhoto.objects.create(inspection=inspection, item=item, image=image)
        return Response(InspectionPhotoSerializer(photo).data, status=status.HTTP_201_CREATED)


class InspectionPhotoDeleteAPIView(OrganizationScopedMixin, generics.DestroyAPIView):
    required_capability = "inspection.update"
    organization_lookup = "inspection__organization"
    queryset = InspectionPhoto.objects.select_related("inspection")
    serializer_class = InspectionPhotoSerializer

    def perform_destroy(self, instance):
        ensure_draft(instance.inspection)
        instance.delete()


class InspectionPhotoFileAPIView(APIView):
    """Image lue par son lien signé (une balise <img> ne transmet pas l'agence active)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(responses={(200, "image/jpeg"): OpenApiTypes.BINARY})
    def get(self, request, token):
        pk = photo_id(token)
        photo = InspectionPhoto.objects.filter(pk=pk).first() if pk else None
        if photo is None or not photo.image.storage.exists(photo.image.name):
            raise Http404
        response = FileResponse(photo.image.open("rb"), content_type="image/jpeg")
        response["Cache-Control"] = "private, max-age=43200"
        response["X-Robots-Tag"] = "noindex"
        return response


class InspectionSignAPIView(InspectionMixin, APIView):
    required_capability = "inspection.update"

    @extend_schema(request=InspectionSignSerializer, responses=InspectionSerializer)
    def post(self, request, pk):
        serializer = InspectionSignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inspection = sign_inspection(self.get_inspection(pk), user=request.user, **serializer.validated_data)
        return Response(InspectionSerializer(self.get_inspection(inspection.pk)).data)


class InspectionReopenAPIView(InspectionMixin, APIView):
    required_capability = "inspection.delete"

    @extend_schema(request=None, responses=InspectionSerializer)
    def post(self, request, pk):
        reopen_inspection(self.get_inspection(pk))
        return Response(InspectionSerializer(self.get_inspection(pk)).data)


class InspectionPdfAPIView(InspectionMixin, APIView):
    required_capability = "inspection.view"

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        return pdf_response(inspection_report(self.get_inspection(pk)))


class InspectionShareAPIView(InspectionMixin, APIView):
    required_capability = "inspection.view"

    @extend_schema(responses=ShareLinkSerializer)
    def get(self, request, pk):
        return Response(ShareLinkSerializer(share_inspection(self.get_inspection(pk))).data)
