from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from imports.commit import apply_import
from imports.plan import build_plan, summarize
from imports.reader import read_file
from imports.template import build_template
from organizations.scoping import OrganizationScopedMixin

from .serializers import ImportCommitSerializer, ImportFileSerializer, ImportPreviewSerializer, ImportSummarySerializer

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ImportTemplateAPIView(OrganizationScopedMixin, APIView):
    """Modèle Excel de reprise d'un parc."""

    required_capability = "portfolio.import"

    @extend_schema(responses={(200, XLSX): OpenApiTypes.BINARY})
    def get(self, request):
        response = HttpResponse(build_template(self.organization), content_type=XLSX)
        response["Content-Disposition"] = 'attachment; filename="dahoo-parc-locatif.xlsx"'
        return response


class ImportPreviewAPIView(OrganizationScopedMixin, APIView):
    """Contrôle d'un fichier : ce qui serait créé et les remarques, ligne par ligne. N'enregistre rien."""

    required_capability = "portfolio.import"
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request=ImportFileSerializer, responses=ImportPreviewSerializer)
    def post(self, request):
        serializer = ImportFileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = build_plan(self.organization, read_file(serializer.validated_data["file"]))
        data = {
            "summary": summarize(plan, self.organization),
            "problems": plan.problems,
            "ignored_columns": plan.ignored_columns,
            "rows": plan.rows,
        }
        return Response(ImportPreviewSerializer(data).data)


class ImportCommitAPIView(OrganizationScopedMixin, APIView):
    """Enregistre le fichier (contrôlé de nouveau) : tout est créé en une fois, ou rien."""

    required_capability = "portfolio.import"
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request=ImportCommitSerializer, responses={201: ImportSummarySerializer})
    def post(self, request):
        serializer = ImportCommitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        options = serializer.validated_data
        summary = apply_import(
            self.organization, read_file(options["file"]), user=request.user,
            first_period=options["first_period"], skip_errors=options["skip_errors"],
        )
        return Response(ImportSummarySerializer(summary).data, status=status.HTTP_201_CREATED)
