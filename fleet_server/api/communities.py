"""Community CRUD endpoints with home listing."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.database import get_db
from fleet_server.repositories.community import CommunityRepository
from fleet_server.schemas.community import (
    CommunityCreate,
    CommunityResponse,
    CommunityUpdate,
)
from fleet_server.schemas.home import HomeResponse

router = APIRouter()


def get_repo(db: AsyncSession = Depends(get_db)) -> CommunityRepository:
    return CommunityRepository(db)


@router.get("/", response_model=list[CommunityResponse])
async def list_communities(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    repo: CommunityRepository = Depends(get_repo),
):
    return await repo.get_all(skip=skip, limit=limit)


@router.get("/{community_id}", response_model=CommunityResponse)
async def get_community(
    community_id: str,
    repo: CommunityRepository = Depends(get_repo),
):
    community = await repo.get_by_id(community_id)
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")
    return community


@router.post("/", response_model=CommunityResponse, status_code=201)
async def create_community(
    payload: CommunityCreate,
    repo: CommunityRepository = Depends(get_repo),
):
    existing = await repo.get_by_id(payload.community_id)
    if existing:
        raise HTTPException(status_code=409, detail="Community already exists")
    return await repo.create(payload.model_dump())


@router.patch("/{community_id}", response_model=CommunityResponse)
async def update_community(
    community_id: str,
    payload: CommunityUpdate,
    repo: CommunityRepository = Depends(get_repo),
):
    community = await repo.update(
        community_id, payload.model_dump(exclude_unset=True)
    )
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")
    return community


@router.delete("/{community_id}", status_code=204)
async def delete_community(
    community_id: str,
    repo: CommunityRepository = Depends(get_repo),
):
    deleted = await repo.delete(community_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Community not found")


@router.get("/{community_id}/homes", response_model=list[HomeResponse])
async def list_community_homes(
    community_id: str,
    repo: CommunityRepository = Depends(get_repo),
):
    homes = await repo.get_homes(community_id)
    if not homes and not await repo.get_by_id(community_id):
        raise HTTPException(status_code=404, detail="Community not found")
    return homes
