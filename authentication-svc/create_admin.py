import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.services import auth_service
from app.models import UserRole
from app.core.config import get_settings

async def main():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        try:
            user, access, refresh, expires = await auth_service.signup(
                session,
                name="Admin User",
                nric="O1234567B",
                passcode="01011980",
                role=UserRole.ORGANISER,
                admin_username="admin",
                admin_password="password",
            )
            await session.commit()
            print(f"Organiser created: {user.id}")
        except ValueError as exc:
            print(f"Failed: {exc}")

asyncio.run(main())
