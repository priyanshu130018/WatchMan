from supabase import create_client
from app.core.config import settings

supabase = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_ANON_KEY
)


class AuthService:

    @staticmethod
    def register(email: str, password: str):
        return supabase.auth.sign_up(
            {
                "email": email,
                "password": password,
            }
        )

    @staticmethod
    def login(email: str, password: str):
        return supabase.auth.sign_in_with_password(
            {
                "email": email,
                "password": password,
            }
        )

    @staticmethod
    def logout():
        return supabase.auth.sign_out()

    @staticmethod
    def current_user(jwt: str):
        return supabase.auth.get_user(jwt)