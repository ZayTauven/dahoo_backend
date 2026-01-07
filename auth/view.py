from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken



from users.services import get_user_capabilities
from dahoo.users.api.serializers import UserSerializer


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(request, email=email, password=password)
        if not user:
            return Response(
                {"detail": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "user": {
                **UserSerializer(user).data,
                "capabilities": get_user_capabilities(user)
            }
        })


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh = RefreshToken(request.data["refresh"])
            refresh.blacklist()
            return Response(status=204)
        except Exception:
            return Response(status=400)



class MeAPIView(APIView):
    def get(self, request):
        user = request.user

        return Response({
            "user": UserSerializer(user).data,
            "capabilities": get_user_capabilities(user),
            "subscription": get_active_subscription(user)
        })
    

class LeaseCreateView(APIView):
    permission_classes = [HasCapability]
    required_capability = "CREATE_LEASE"

