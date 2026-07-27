from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class BearerTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('authorization')

        if not auth_header:
            raise AuthenticationFailed('Authorization header is required.')

        # Ensure the header starts with "Bearer "
        if not auth_header.startswith('Bearer '):
            raise AuthenticationFailed('Invalid token header. No Bearer token found.')

        # Extract the token
        token = auth_header.split(' ')[1]

        # Validate the token
        if token != 'D81BiVu9uXmQx6H2WYfN2kkKZESHrZpiHYSp0bw6aWf39kHtWU':
            raise AuthenticationFailed('Invalid or expired token.')

        # Return a dummy user object (or None if no user is associated with the token)
        return (None, None)
