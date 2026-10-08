"""Print a one-time password reset link, for an admin locked out of their account.

    docker exec inskect-api python -m app.auth.reset_link you@example.com

(In the development containers, `uv run python -m …`.)

Open the printed path on your Inskect address within 24 hours to choose a new password.
"""

from __future__ import annotations

import sys

from app import auth, db


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m app.auth.reset_link <email>", file=sys.stderr)
        return 2
    db.init_db()
    try:
        user = db.get_user_by_email(auth.normalize_email(argv[1]))
    except auth.AuthError as exc:
        print(exc, file=sys.stderr)
        return 1
    if user is None:
        print(f"No account with the email {argv[1]}", file=sys.stderr)
        return 1
    token, _ = auth.issue_password_reset(user["id"])
    print(f"Reset link for {user['email']} ({user['role']}), valid for {auth.RESET_LINK_HOURS} hours:")
    print(auth.reset_link_path(token))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
