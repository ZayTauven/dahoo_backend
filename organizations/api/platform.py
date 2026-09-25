"""
Espace plateforme : réservé à l'équipe Dahoo (éditeur du SaaS, utilisateurs `is_staff`).
Création des agences et de leur premier administrateur, suivi des essais et des abonnements.
"""

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from access.models import Role
from access.permissions import IsPlatformAdmin
from organizations.models import Membership, Organization
from organizations.platform_dashboard import build_platform_dashboard
from organizations.services import add_member, validate_new_member
from public.models import DemoRequest
from subscriptions.models import Subscription, SubscriptionPlan
from subscriptions.services import get_access_status

from .serializers import MembershipSerializer, NewMemberFieldsMixin

ACCESS_STATUS_FIELD = serializers.ChoiceField(choices=["ACTIVE", "TRIAL", "EXPIRED"])


# --- Sérialiseurs


class PlatformOrganizationSerializer(serializers.ModelSerializer):
    access_status = serializers.SerializerMethodField()
    member_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Organization
        fields = [
            "id", "name", "phone", "email", "address", "city",
            "is_active", "is_internal", "trial_ends_at", "access_status", "member_count", "created_at",
        ]
        read_only_fields = ["created_at"]

    @extend_schema_field(ACCESS_STATUS_FIELD)
    def get_access_status(self, organization):
        return get_access_status(organization)


class OrganizationAdminSerializer(NewMemberFieldsMixin):
    """Premier administrateur de l'agence : compte existant (par téléphone) ou nouveau compte."""


class PlatformOrganizationCreateSerializer(PlatformOrganizationSerializer):
    admin = OrganizationAdminSerializer(write_only=True)

    class Meta(PlatformOrganizationSerializer.Meta):
        fields = PlatformOrganizationSerializer.Meta.fields + ["admin"]
        # La fin d'essai est calculée à la création (TRIAL_DAYS) ; elle se prolonge ensuite par PATCH.
        read_only_fields = ["trial_ends_at", "created_at"]

    def validate_admin(self, admin):
        admin["existing_user"] = validate_new_member(None, admin)
        return admin

    @transaction.atomic
    def create(self, validated_data):
        admin = validated_data.pop("admin")
        organization = Organization.objects.create(**validated_data)
        add_member(organization, Role.objects.get(code="ORG_ADMIN"), **admin)
        return organization


class PlatformSubscriptionSerializer(serializers.ModelSerializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=SubscriptionPlan.objects.all())

    class Meta:
        model = Subscription
        fields = ["id", "organization", "plan", "status", "start_date", "end_date", "created_at"]
        read_only_fields = ["organization", "created_at"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "La fin doit être postérieure au début."})
        return attrs


class PlatformDemoRequestSerializer(serializers.ModelSerializer):
    """Demande de démo reçue par la vitrine ; seul `handled` est modifiable."""

    class Meta:
        model = DemoRequest
        fields = [
            "id", "agency_name", "contact_name", "phone", "email", "city",
            "units_range", "message", "created_at", "handled",
        ]
        read_only_fields = [field for field in fields if field != "handled"]


# --- Tableau de bord de la plateforme (organizations/platform_dashboard.py), lecture seule.

PLATFORM_MONEY = {"max_digits": 16, "decimal_places": 2}
AGENCY_STATUS = [("ACTIVE", "Abonnée"), ("TRIAL", "En essai"), ("EXPIRED", "Essai expiré"), ("SUSPENDED", "Suspendue")]


class AgencyStatusCountsSerializer(serializers.Serializer):
    ACTIVE = serializers.IntegerField()
    TRIAL = serializers.IntegerField()
    EXPIRED = serializers.IntegerField()
    SUSPENDED = serializers.IntegerField()


class PlatformAgenciesSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    by_status = AgencyStatusCountsSerializer()
    members = serializers.IntegerField()
    cities = serializers.IntegerField()


class TrialEndingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    city = serializers.CharField()
    days_left = serializers.IntegerField()
    members = serializers.IntegerField()
    listings = serializers.IntegerField()


class PlatformMonthSerializer(serializers.Serializer):
    month = serializers.CharField(help_text="AAAA-MM")
    signups = serializers.IntegerField()
    demo_requests = serializers.IntegerField()


class PlanRevenueSerializer(serializers.Serializer):
    plan = serializers.CharField()
    count = serializers.IntegerField()
    mrr = serializers.DecimalField(**PLATFORM_MONEY)


class PlatformSubscriptionsSummarySerializer(serializers.Serializer):
    active = serializers.IntegerField()
    mrr = serializers.DecimalField(**PLATFORM_MONEY)
    by_plan = PlanRevenueSerializer(many=True)


class PendingDemoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    agency_name = serializers.CharField()
    contact_name = serializers.CharField()
    city = serializers.CharField()
    units_range = serializers.CharField()
    created_at = serializers.DateTimeField()


class PlatformDemoSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    pending = serializers.IntegerField()
    last_30d = serializers.IntegerField()
    recent_pending = PendingDemoSerializer(many=True)


class PlatformPortalSerializer(serializers.Serializer):
    listings_published = serializers.IntegerField()
    listings_rent = serializers.IntegerField()
    listings_sale = serializers.IntegerField()
    interests_30d = serializers.IntegerField()
    units_managed = serializers.IntegerField()
    payments_30d_amount = serializers.DecimalField(**PLATFORM_MONEY)
    payments_30d_count = serializers.IntegerField()


class TopAgencySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    city = serializers.CharField()
    logo = serializers.URLField(allow_null=True)
    status = serializers.ChoiceField(choices=AGENCY_STATUS)
    members = serializers.IntegerField()
    units = serializers.IntegerField()
    listings = serializers.IntegerField()


class PlatformDashboardSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    months = serializers.IntegerField()
    agencies = PlatformAgenciesSerializer()
    trials_ending = TrialEndingSerializer(many=True)
    monthly = PlatformMonthSerializer(many=True)
    subscriptions = PlatformSubscriptionsSummarySerializer()
    demo_requests = PlatformDemoSummarySerializer()
    portal = PlatformPortalSerializer()
    top_agencies = TopAgencySerializer(many=True)


# --- Vues


class PlatformOrganizationListCreateAPIView(generics.ListCreateAPIView):
    """Liste des agences (filtre ?search=) et création d'une agence avec son administrateur."""

    permission_classes = [IsPlatformAdmin]

    def get_queryset(self):
        queryset = Organization.objects.annotate(
            member_count=Count("memberships", filter=Q(memberships__is_active=True))
        ).order_by("name")
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(city__icontains=search))
        return queryset

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PlatformOrganizationCreateSerializer
        return PlatformOrganizationSerializer

    @extend_schema(request=PlatformOrganizationCreateSerializer, responses={201: PlatformOrganizationSerializer})
    def post(self, request, *args, **kwargs):
        serializer = PlatformOrganizationCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        organization = self.get_queryset().get(pk=serializer.save().pk)  # relu avec member_count
        return Response(PlatformOrganizationSerializer(organization).data, status=status.HTTP_201_CREATED)


class PlatformOrganizationDetailAPIView(generics.RetrieveUpdateAPIView):
    """Modifier une agence : prolonger l'essai (trial_ends_at), suspendre (is_active=false)..."""

    permission_classes = [IsPlatformAdmin]
    serializer_class = PlatformOrganizationSerializer

    def get_queryset(self):
        return Organization.objects.annotate(
            member_count=Count("memberships", filter=Q(memberships__is_active=True))
        )


class PlatformOrganizationMembersAPIView(generics.ListAPIView):
    """Membres d'une agence (support)."""

    permission_classes = [IsPlatformAdmin]
    serializer_class = MembershipSerializer
    queryset = Membership.objects.none()  # Modèle de référence pour le schéma OpenAPI (le vrai queryset dépend de la requête).

    def get_queryset(self):
        return Membership.objects.filter(organization_id=self.kwargs["pk"]).select_related("user", "role").order_by("id")


class PlatformSubscriptionListCreateAPIView(generics.ListCreateAPIView):
    """Abonnements d'une agence ; en créer un débloque l'accès après l'essai."""

    permission_classes = [IsPlatformAdmin]
    serializer_class = PlatformSubscriptionSerializer
    queryset = Subscription.objects.none()  # Modèle de référence pour le schéma OpenAPI (le vrai queryset dépend de la requête).

    def get_organization(self):
        return get_object_or_404(Organization, pk=self.kwargs["pk"])

    def get_queryset(self):
        return Subscription.objects.filter(organization=self.get_organization()).order_by("-start_date")

    def perform_create(self, serializer):
        serializer.save(organization=self.get_organization())


class PlatformSubscriptionDetailAPIView(generics.RetrieveUpdateAPIView):
    """Suspendre, prolonger ou changer de plan."""

    permission_classes = [IsPlatformAdmin]
    serializer_class = PlatformSubscriptionSerializer
    queryset = Subscription.objects.all()


class PlatformDemoRequestListAPIView(generics.ListAPIView):
    """Demandes de démo de la vitrine (filtre ?handled=, recherche ?search=), les plus récentes d'abord."""

    permission_classes = [IsPlatformAdmin]
    serializer_class = PlatformDemoRequestSerializer
    queryset = DemoRequest.objects.order_by("-created_at")
    filterset_fields = ["handled", "units_range"]
    search_fields = ["agency_name", "contact_name", "phone", "email", "city"]


class PlatformDemoRequestDetailAPIView(generics.RetrieveUpdateAPIView):
    """Marquer une demande comme traitée (PATCH {"handled": true})."""

    permission_classes = [IsPlatformAdmin]
    serializer_class = PlatformDemoRequestSerializer
    queryset = DemoRequest.objects.all()
    http_method_names = ["get", "patch", "head", "options"]


class PlatformDashboardAPIView(APIView):
    """Tableau de bord de l'équipe Dahoo : agences, essais, abonnements, démos et activité du portail."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        parameters=[OpenApiParameter("months", int, description="Nombre de mois d'historique : 6 ou 12 (défaut 12).")],
        responses=PlatformDashboardSerializer,
    )
    def get(self, request):
        try:
            months = int(request.query_params.get("months", 12))
        except ValueError:
            months = 12
        data = build_platform_dashboard(months=6 if months <= 6 else 12, request=request)
        return Response(PlatformDashboardSerializer(data).data)
