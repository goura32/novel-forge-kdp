from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class World(BaseModel):
    summary: str
    rules: list[str] = Field(default_factory=list)


class Character(BaseModel):
    name: str
    role: str
    arc: str


class PlannedVolume(BaseModel):
    number: int
    title: str
    premise: str


class SeriesPlan(BaseModel):
    title: str
    slug: str
    logline: str
    genre: str
    target_audience: str
    themes: list[str]
    selling_points: list[str]
    world: World
    main_characters: list[Character]
    planned_volumes: list[PlannedVolume]


class ScenePlan(BaseModel):
    number: int
    title: str
    pov: str
    goal: str
    conflict: str
    outcome: str


class ChapterPlan(BaseModel):
    number: int
    title: str
    purpose: str
    scenes: list[ScenePlan]


class VolumeOutline(BaseModel):
    volume_number: int
    title: str
    chapters: list[ChapterPlan]


class SceneProgress(BaseModel):
    chapter: int
    scene: int
    title: str
    status: Literal["planned", "drafted", "reviewed", "revised"] = "planned"
    path: str | None = None


class VolumeProgress(BaseModel):
    number: int
    title: str
    status: Literal["planned", "outlined", "drafted", "reviewed", "revised"] = "planned"
    scenes: list[SceneProgress] = Field(default_factory=list)


class ProjectState(BaseModel):
    series: SeriesPlan
    current_volume: int = 1
    volumes: list[VolumeProgress] = Field(default_factory=list)
