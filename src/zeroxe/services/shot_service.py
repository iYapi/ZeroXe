"""Shot and Asset Data Service.

Provides fast, optimized querying and in-memory caching for episodes, sequences, and shots.
"""

import logging
from typing import Dict, List, Optional
import gazu
from zeroxe.api.gazu_client import is_kitsu_connected
from zeroxe.models.shot_model import Episode, Sequence, Shot

logger = logging.getLogger(__name__)


class ShotService:
    # In-memory cache to make switching between projects and episodes instant (0ms)
    _episode_cache: Dict[str, List[Episode]] = {}
    _sequence_cache: Dict[str, List[Sequence]] = {}
    _shot_cache: Dict[str, List[Shot]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached episode, sequence, and shot data."""
        cls._episode_cache.clear()
        cls._sequence_cache.clear()
        cls._shot_cache.clear()

    @classmethod
    def get_episodes_by_project_id(cls, project_id: str, use_cache: bool = True) -> List[Episode]:
        """Fetch all episodes for a project with optional in-memory caching."""
        if not is_kitsu_connected() or not project_id:
            return []

        if use_cache and project_id in cls._episode_cache:
            return cls._episode_cache[project_id]

        try:
            raw_episodes = gazu.context.all_episodes_for_project(project_id) or []
            episodes = [Episode.from_kitsu(p) for p in raw_episodes]
            cls._episode_cache[project_id] = episodes
            return episodes
        except Exception as e:
            logger.error(f"Failed to fetch episodes for project {project_id}: {e}")
            return []

    @classmethod
    def get_sequences_by_episode_id(cls, episode_id: str, use_cache: bool = True) -> List[Sequence]:
        """Fetch all sequences for an episode with optional in-memory caching."""
        if not is_kitsu_connected() or not episode_id:
            return []

        if use_cache and episode_id in cls._sequence_cache:
            return cls._sequence_cache[episode_id]

        try:
            raw_sequences = gazu.context.all_sequences_for_episode(episode_id) or []
            sequences = [Sequence.from_kitsu(p) for p in raw_sequences]
            cls._sequence_cache[episode_id] = sequences
            return sequences
        except Exception as e:
            logger.error(f"Failed to fetch sequences for episode {episode_id}: {e}")
            return []

    @classmethod
    def get_shots_by_episode_id(
        cls,
        episode_id: str,
        episode_name: str = "",
        use_cache: bool = True,
    ) -> List[Shot]:
        """Fetch and map all shots for an episode in a single optimized query.

        Avoids the N+1 network request bottleneck by pre-mapping sequence names in O(1).
        """
        if not is_kitsu_connected() or not episode_id:
            return []

        if use_cache and episode_id in cls._shot_cache:
            return cls._shot_cache[episode_id]

        try:
            # 1. Fetch shots and sequences in parallel/batch (2 queries total)
            shots_raw = gazu.shot.all_shots_for_episode(episode_id) or []
            sequences = cls.get_sequences_by_episode_id(episode_id, use_cache=use_cache)

            # Build fast O(1) sequence lookup map
            seq_map: Dict[str, str] = {
                seq.id: seq.name
                for seq in sequences
                if seq.id
            }

            # 2. Get episode name if not supplied
            if not episode_name:
                try:
                    ep_data = gazu.shot.get_episode(episode_id)
                    episode_name = ep_data.get("name", "") if isinstance(ep_data, dict) else getattr(ep_data, "name", "")
                except Exception:
                    episode_name = ""

            # 3. Map shots without blocking HTTP loops
            mapped_shots: List[Shot] = []
            for shot in shots_raw:
                if not isinstance(shot, dict):
                    continue

                parent_id = shot.get("parent_id", "")
                seq_name = seq_map.get(parent_id, "")

                shot_dict = dict(shot)
                shot_dict["sequence"] = seq_name
                shot_dict["episode_id"] = episode_id
                shot_dict["episode"] = episode_name
                # Keep assets list empty for initial list load; fetch on-demand when clicked
                shot_dict["assets"] = shot.get("assets", []) if isinstance(shot.get("assets"), list) else []

                mapped_shots.append(Shot.from_kitsu(shot_dict))

            cls._shot_cache[episode_id] = mapped_shots
            return mapped_shots

        except Exception as e:
            logger.error(f"Failed to fetch shots for episode {episode_id}: {e}")
            return []

    @classmethod
    def get_shots_by_sequence(
        cls,
        sequence_id: Optional[str] = None,
        episode_id: Optional[str] = None,
        episode: Optional[str] = None,
        sequence: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[Shot]:
        """Fetch all shots for a sequence or episode from Kitsu."""
        if not is_kitsu_connected():
            return []

        # 1. Direct sequence_id
        if sequence_id:
            try:
                raw_shots = gazu.shot.all_shots_for_sequence(sequence_id) or []
                return [Shot.from_kitsu(s) for s in raw_shots if isinstance(s, dict)]
            except Exception as e:
                logger.error(f"Failed to fetch shots for sequence {sequence_id}: {e}")

        # 2. Episode ID
        if episode_id:
            all_ep_shots = cls.get_shots_by_episode_id(episode_id, episode_name=episode or "")
            if sequence:
                seq_clean = sequence.strip().lower()
                return [s for s in all_ep_shots if s.sequence and s.sequence.lower() == seq_clean]
            return all_ep_shots

        # 3. Search via episode name
        if episode and project_id:
            episodes = cls.get_episodes_by_project_id(project_id)
            target_ep = next((e for e in episodes if e.name.lower() == episode.lower() or e.id == episode), None)
            if target_ep:
                all_ep_shots = cls.get_shots_by_episode_id(target_ep.id, episode_name=target_ep.name)
                if sequence:
                    seq_clean = sequence.strip().lower()
                    return [s for s in all_ep_shots if s.sequence and s.sequence.lower() == seq_clean]
                return all_ep_shots

        return []

    @classmethod
    def get_assets_for_shot(cls, shot_id: str) -> List[dict]:
        """Fetch assets linked to a specific shot on-demand when inspected."""
        if not is_kitsu_connected() or not shot_id:
            return []

        try:
            raw_assets = gazu.asset.all_assets_for_shot(shot_id) or []
            return [
                {
                    "id": a.get("id") if isinstance(a, dict) else getattr(a, "id", ""),
                    "name": a.get("name") if isinstance(a, dict) else getattr(a, "name", ""),
                    "entity_type_id": (
                        a.get("entity_type_id") if isinstance(a, dict) else getattr(a, "entity_type_id", None)
                    ),
                }
                for a in raw_assets
            ]
        except Exception as e:
            logger.warning(f"Could not load assets for shot {shot_id}: {e}")
            return []