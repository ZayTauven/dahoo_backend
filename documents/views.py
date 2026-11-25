from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from dahoo.throttling import AnonRateThrottle, ScopedRateThrottle
from documents.http import pdf_response
from documents.receipts import document_from_token


class SharedDocumentAPIView(APIView):
    """Document ouvert par son lien signé, sans compte (quittance, reçu, relevé)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "shared_document"

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, token):
        return pdf_response(document_from_token(token))
