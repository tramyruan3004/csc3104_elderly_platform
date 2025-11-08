import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.services import auth_service
from app.models import (
    UserRole,
    Organization,
    OrgMember,
    Credential,
    User,
)
from app.core.config import get_settings

ORG_NAME = "Demo Organiser Org"


async def main():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        try:
            # Create or fetch an organisation
            org = (
                await session.execute(select(Organization).where(Organization.name == ORG_NAME))
            ).scalar_one_or_none()
            if not org:
                org = Organization(name=ORG_NAME)
                session.add(org)
                await session.flush()

            admin_cred = (
                await session.execute(
                    select(Credential).where(Credential.admin_username == "admin")
                )
            ).scalar_one_or_none()

            created_new_user = False
            if admin_cred:
                user = await session.get(User, admin_cred.user_id)
            else:
                user, *_ = await auth_service.signup(
                    session,
                    name="Admin User",
                    nric="O1234567B",
                    passcode="01011980",
                    role=UserRole.ORGANISER,
                    admin_username="admin",
                    admin_password="password",
                )
                created_new_user = True

            # Ensure membership record exists
            existing_membership = (
                await session.execute(
                    select(OrgMember).where(
                        OrgMember.org_id == org.id,
                        OrgMember.user_id == user.id,
                    )
                )
            ).scalar_one_or_none()
            if not existing_membership:
                session.add(
                    OrgMember(
                        org_id=org.id,
                        user_id=user.id,
                        role_in_org=UserRole.ORGANISER,
                    )
                )

            await session.commit()

            action = "created" if created_new_user else "reused"
            print(
                f"Organiser {action}: {user.id} now assigned to organisation '{org.name}' ({org.id})"
            )
        except Exception as exc:
            await session.rollback()
            raise


if __name__ == "__main__":
    # psycopg async connection requires selector loop on Windows
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
