import argparse
import getpass

from app.infrastructure.database.session import SessionFactory
from app.modules.identity.service import ClientContext, IdentityConflict, create_initial_admin


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="إنشاء أول مدير لنظام PipeERP. لا تُمرر كلمة المرور في سطر الأوامر.",
    )
    command.add_argument("--username", required=True)
    command.add_argument("--display-name", required=True)
    return command


def main() -> int:
    args = parser().parse_args()
    password = getpass.getpass("كلمة مرور المدير (12 حرفًا على الأقل): ")
    confirmation = getpass.getpass("أعد إدخال كلمة المرور: ")
    if password != confirmation:
        print("كلمتا المرور غير متطابقتين")
        return 2
    try:
        with SessionFactory.begin() as db:
            user = create_initial_admin(
                db,
                username=args.username,
                display_name=args.display_name,
                password=password,
                client=ClientContext("local-bootstrap", "pipeerp-bootstrap", None),
            )
    except (IdentityConflict, ValueError) as exc:
        print(str(exc))
        return 1
    print(f"تم إنشاء المدير: {user.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
