import asyncio

from sqlalchemy import select

from fleet_server.database import async_session
from fleet_server.models import Community, Device, FirmwareVersion, Home, User, home_community
from fleet_server.services.auth import hash_password


async def seed():
    async with async_session() as session:
        existing = await session.execute(select(Community))
        if existing.scalars().first():
            print("Database already seeded, skipping.")
            return

        # Communities
        communities = [
            Community(
                community_id="nrh",
                name="NRH",
                description="Neuro Rehab Hospital patients",
            ),
            Community(
                community_id="kaiser",
                name="Kaiser Permanente",
                description="Kaiser patients in smart home program",
            ),
            Community(
                community_id="stjude",
                name="St Jude",
                description="St Jude affiliated patients",
            ),
            Community(
                community_id="sutterhealth",
                name="Sutter Health",
                description="Sutter Health patients",
            ),
            Community(
                community_id="all",
                name="All Homes",
                description="Broadcast to entire fleet",
            ),
        ]
        session.add_all(communities)
        await session.flush()

        # Homes
        home_a = Home(
            home_id="home-001",
            patient_name="Test Patient A",
            address="123 NRH Lane, Salt Lake City, UT",
        )
        home_b = Home(
            home_id="home-002",
            patient_name="Test Patient B",
            address="456 Kaiser Blvd, San Francisco, CA",
        )
        home_c = Home(
            home_id="home-003",
            patient_name="Test Patient C",
            address="789 Multi Ave, Sacramento, CA",
        )
        session.add_all([home_a, home_b, home_c])
        await session.flush()

        # Home-community assignments
        await session.execute(
            home_community.insert().values(
                [
                    {"home_id": "home-001", "community_id": "nrh"},
                    {"home_id": "home-001", "community_id": "all"},
                    {"home_id": "home-002", "community_id": "kaiser"},
                    {"home_id": "home-002", "community_id": "all"},
                    {"home_id": "home-003", "community_id": "nrh"},
                    {"home_id": "home-003", "community_id": "sutterhealth"},
                    {"home_id": "home-003", "community_id": "all"},
                ]
            )
        )

        # Devices
        devices = [
            Device(
                device_id="esp32-living-room-001",
                mac="AA:BB:CC:DD:E0:01",
                firmware_version="1.0.0",
                role="hub",
                status="unknown",
                home_id="home-001",
            ),
            Device(
                device_id="esp32-fall-sensor-001",
                mac="AA:BB:CC:DD:E0:02",
                firmware_version="1.0.0",
                role="sensor",
                status="unknown",
                home_id="home-001",
            ),
            Device(
                device_id="esp32-motion-002",
                mac="AA:BB:CC:DD:E0:03",
                firmware_version="1.0.0",
                role="sensor",
                status="unknown",
                home_id="home-002",
            ),
            Device(
                device_id="esp32-door-003",
                mac="AA:BB:CC:DD:E0:04",
                firmware_version="1.0.0",
                role="sensor",
                status="unknown",
                home_id="home-003",
            ),
        ]
        session.add_all(devices)

        # Firmware
        fw = FirmwareVersion(
            version="1.0.0",
            binary_path="./data/firmware/1.0.0/firmware.bin",
            checksum="placeholder-sha256",
            release_notes="Initial firmware release",
        )
        session.add(fw)

        # Users
        users = [
            User(
                id="admin",
                email="admin@tetradapt.com",
                hashed_password=hash_password("admin123"),
                role="admin",
            ),
            User(
                id="operator1",
                email="operator@tetradapt.com",
                hashed_password=hash_password("operator123"),
                role="operator",
            ),
            User(
                id="viewer1",
                email="viewer@tetradapt.com",
                hashed_password=hash_password("viewer123"),
                role="viewer",
            ),
        ]
        session.add_all(users)

        await session.commit()
        print("Seed complete: 5 communities, 3 homes, 4 devices, 1 firmware, 3 users")


if __name__ == "__main__":
    asyncio.run(seed())
