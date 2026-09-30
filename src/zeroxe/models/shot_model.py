from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Shot:
    id: str
    name: str
    sequence_id: str
    sequence: str
    episode_id: str
    episode: str
    preview_file_id: str
    resolution: str
    fps: int
    frame_in: int
    frame_out: int
    assets: List
    # set: str
    # char: str
    # prop: str
    # ms_lit: str
    # ms_comp: str

    @classmethod
    def from_kitsu(cls, data: Dict[str, Any]) -> "Shot":
        custom_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            sequence_id=data.get("parent_id", ""),
            sequence=data.get("sequence", ""),
            episode_id=data.get("episode_id", ""),
            episode=data.get("episode", ""),
            preview_file_id=data.get("preview_file_id", "") or "",
            resolution=str(custom_data.get("resolution", "") or ""),
            fps=int(custom_data.get("fps") or 0),
            frame_in=int(custom_data.get("frame_in") or 0),
            frame_out=int(custom_data.get("frame_out") or 0),
            assets=data.get("assets", []) if isinstance(data.get("assets"), list) else [],
            # set=data.get("set", ""),
            # char=data.get("char", ""),
            # prop=data.get("prop", ""),
            # ms_lit=data.get("ms_lit", ""),
            # ms_comp=data.get("ms_comp", ""),
        )


@dataclass
class Episode:
    id: str
    name: str
    project_id: str

    @classmethod
    def from_kitsu(cls, data: Dict[str, Any]) -> "Episode":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            project_id=data.get("project_id", ""),
        )


@dataclass
class Sequence:
    id: str
    name: str
    episode_id: str
    project_id: str

    @classmethod
    def from_kitsu(cls, data: Dict[str, Any]) -> "Sequence":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            episode_id=data.get("parent_id", ""),
            project_id=data.get("project_id", ""),
        )