from models import User
from routes.shared import to_user_out
from schemas import UserOut


def get_me_route(current_user: User) -> UserOut:
    return to_user_out(current_user)
