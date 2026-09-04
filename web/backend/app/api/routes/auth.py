import hmac
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.dependencies import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    CurrentPrincipal,
    DatabaseSession,
    client_context,
    enforce_csrf,
)
from app.core.settings import Settings, get_settings
from app.modules.identity.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
)
from app.modules.identity.security import create_access_token
from app.modules.identity.service import (
    AuthenticationFailed,
    RateLimitExceeded,
    authenticate,
    change_own_password,
    refresh_authentication,
    revoke_session,
    user_view,
)

router = APIRouter(prefix="/auth")


def _set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    settings: Settings,
) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        path="/api",
        secure=settings.secure_cookies,
        samesite="strict",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_session_hours * 3600,
        httponly=True,
        path="/api/v1/auth",
        secure=settings.secure_cookies,
        samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=settings.refresh_session_hours * 3600,
        httponly=False,
        path="/",
        secure=settings.secure_cookies,
        samesite="strict",
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        ACCESS_COOKIE,
        path="/api",
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        path="/api/v1/auth",
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        httponly=False,
        secure=settings.secure_cookies,
        samesite="strict",
    )


def _access_token(result_user_id: UUID, result_session_id: UUID, version: int) -> str:
    settings = get_settings()
    return create_access_token(
        user_id=result_user_id,
        session_id=result_session_id,
        user_version=version,
        secret_key=settings.secret_key,
        lifetime_minutes=settings.access_token_minutes,
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DatabaseSession,
) -> LoginResponse:
    settings = get_settings()
    try:
        result = authenticate(
            db,
            username=payload.username,
            password=payload.password,
            client=client_context(request),
            session_hours=settings.refresh_session_hours,
            max_attempts=settings.login_max_attempts,
            lock_minutes=settings.login_lock_minutes,
        )
    except RateLimitExceeded:
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "محاولات كثيرة؛ حاول لاحقًا",
        ) from None
    except (AuthenticationFailed, ValueError):
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "بيانات الدخول غير صحيحة") from None
    view = user_view(db, result.principal.user)
    db.commit()
    access_token = _access_token(
        result.principal.user.id,
        result.principal.auth_session.id,
        result.principal.user.version,
    )
    _set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=result.secrets.refresh_token,
        csrf_token=result.secrets.csrf_token,
        settings=settings,
    )
    return LoginResponse(user=view)


@router.get("/me", response_model=LoginResponse)
def me(principal: CurrentPrincipal, db: DatabaseSession) -> LoginResponse:
    return LoginResponse(user=user_view(db, principal.user))


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    request: Request,
    response: Response,
    db: DatabaseSession,
) -> LoginResponse:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    header_csrf = request.headers.get("x-csrf-token")
    cookie_csrf = request.cookies.get(CSRF_COOKIE)
    if (
        refresh_token is None
        or header_csrf is None
        or cookie_csrf is None
        or not hmac.compare_digest(header_csrf, cookie_csrf)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "تعذر تجديد الجلسة")
    try:
        result = refresh_authentication(
            db,
            refresh_token=refresh_token,
            csrf_token=header_csrf,
            client=client_context(request),
        )
    except AuthenticationFailed:
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "تعذر تجديد الجلسة") from None
    view = user_view(db, result.principal.user)
    db.commit()
    settings = get_settings()
    _set_auth_cookies(
        response,
        access_token=_access_token(
            result.principal.user.id,
            result.principal.auth_session.id,
            result.principal.user.version,
        ),
        refresh_token=result.secrets.refresh_token,
        csrf_token=result.secrets.csrf_token,
        settings=settings,
    )
    return LoginResponse(user=view)


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, db: DatabaseSession) -> MessageResponse:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    header_csrf = request.headers.get("x-csrf-token")
    cookie_csrf = request.cookies.get(CSRF_COOKIE)
    if (
        refresh_token is None
        or header_csrf is None
        or cookie_csrf is None
        or not hmac.compare_digest(header_csrf, cookie_csrf)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "رمز الحماية غير صالح")
    try:
        revoke_session(
            db,
            refresh_token=refresh_token,
            csrf_token=header_csrf,
            client=client_context(request),
        )
    except AuthenticationFailed:
        db.rollback()
    else:
        db.commit()
    _clear_auth_cookies(response, get_settings())
    return MessageResponse(message="تم تسجيل الخروج")


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> MessageResponse:
    enforce_csrf(request, db, principal)
    try:
        change_own_password(
            db,
            principal=principal,
            current_password=payload.current_password,
            new_password=payload.new_password,
            client=client_context(request),
        )
    except AuthenticationFailed:
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "كلمة المرور الحالية غير صحيحة") from None
    db.commit()
    _clear_auth_cookies(response, get_settings())
    return MessageResponse(message="تم تغيير كلمة المرور؛ سجّل الدخول مرة أخرى")
