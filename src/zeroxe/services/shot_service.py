from typing import List, Optional
import gazu
from zeroxe.models.shot_model import Shot, Episode, Sequence

class ShotService:
    @staticmethod
    def get_episodes_by_project_id(project_id: str) -> List[Episode]:
        raw_episodes = gazu.context.all_episodes_for_project(project_id)
        return [Episode.from_kitsu(p) for p in raw_episodes]

    @staticmethod
    def get_sequences_by_episode_id(episode_id: str) -> List[Sequence]:
        raw_sequences = gazu.context.all_sequences_for_episode(episode_id)
        return [Sequence.from_kitsu(p) for p in raw_sequences]

    @staticmethod
    def get_shots_by_episode_id(episode_id: str) -> List[Shot]:
        shots = gazu.shot.all_shots_for_episode(episode_id)
        sequences = ShotService.get_sequences_by_episode_id(episode_id)
        episode = gazu.shot.get_episode(episode_id)
        seq_map = {
            getattr(seq, "id", seq.get("id") if isinstance(seq, dict) else None): (
                getattr(seq, "name", seq.get("name") if isinstance(seq, dict) else None)
            )
            for seq in sequences
        }
        episode_name = episode.get("name") if isinstance(episode, dict) else episode.name
        updated_shots = []
        for shot in shots:
            parent_id = shot.get("parent_id") if isinstance(shot, dict) else getattr(shot, "parent_id", None)
            if parent_id in seq_map:
                shot_data = dict(shot) if isinstance(shot, dict) else shot.__dict__.copy()
                shot_data["sequence"] = seq_map[parent_id]
                shot_data["episode_id"] = episode_id
                shot_data["episode"] = episode_name

                raw_assets = gazu.asset.all_assets_for_shot(shot.get("id", ""))
                shot_data["assets"] = [
                    {
                        "id": asset.get("id") if isinstance(asset, dict) else asset.id,
                        "name": asset.get("name") if isinstance(asset, dict) else asset.name,
                        "entity_type_id": (
                            asset.get("entity_type_id")
                            if isinstance(asset, dict)
                            else getattr(asset, "entity_type_id", None)
                        ),
                    }
                    for asset in raw_assets
                ]

                updated_shots.append(shot_data)
        return [Shot.from_kitsu(p) for p in updated_shots]