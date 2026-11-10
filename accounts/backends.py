from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class UsernameOrEmailBackend(ModelBackend):
    """Lets users log in with either their username or their email address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or password is None:
            return None

        candidates = list(User.objects.filter(Q(username=username) | Q(email__iexact=username)))
        for user in candidates:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        if not candidates:
            # Same work as a real check, so response times don't reveal which accounts exist.
            User().set_password(password)
        return None
