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
    fps: float
    frame_in: float
    frame_out: float
    assets: List
    # set: str
    # char: str
    # prop: str
    # ms_lit: str
    # ms_comp: str

    @classmethod
    def from_kitsu(cls, data: Dict[str, Any]) -> "Shot":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            sequence_id=data.get("parent_id", ""),
            sequence=data.get("sequence", ""),
            episode_id=data.get("episode_id", ""),
            episode=data.get("episode", ""),
            preview_file_id=data.get("preview_file_id", ""),
            resolution=data.get("data", {}).get("resolution", ""),
            fps=data.get("data", {}).get("fps", 0),
            frame_in=data.get("data", {}).get("frame_in", 0),
            frame_out=data.get("data", {}).get("frame_out", 0),
            assets=data.get("assets", []),
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
            project_id=data.get("project_id", "")
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
            project_id=data.get("project_id", "")
        )