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
    _project_shot_cache: Dict[str, List[Shot]] = {}
    _project_sequence_cache: Dict[str, List[Sequence]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached episode, sequence, and shot data."""
        cls._episode_cache.clear()
        cls._sequence_cache.clear()
        cls._shot_cache.clear()
        cls._project_shot_cache.clear()
        cls._project_sequence_cache.clear()

    @classmethod
    def get_episodes_by_project_id(cls, project_id: str, use_cache: bool = True) -> List[Episode]:
        """Fetch all episodes for a project with optional in-memory caching."""
        if not project_id:
            return []

        if use_cache and project_id in cls._episode_cache:
            return cls._episode_cache[project_id]

        if not is_kitsu_connected():
            return []

        try:
            raw_episodes = gazu.context.all_episodes_for_project(project_id) or []
            episodes = [Episode.from_kitsu(p) for p in raw_episodes if isinstance(p, dict)]
            cls._episode_cache[project_id] = episodes
            return episodes
        except Exception as e:
            logger.error(f"Failed to fetch episodes for project {project_id}: {e}")
            return []

    @classmethod
    def get_sequences_by_project_id(cls, project_id: str, use_cache: bool = True) -> List[Sequence]:
        """Fetch all sequences for a project with optional in-memory caching."""
        if not project_id:
            return []

        if use_cache and project_id in cls._project_sequence_cache:
            return cls._project_sequence_cache[project_id]

        if not is_kitsu_connected():
            return []

        try:
            try:
                raw_sequences = gazu.shot.all_sequences_for_project(project_id) or []
            except Exception:
                raw_sequences = gazu.context.all_sequences_for_project(project_id) or []

            sequences = [Sequence.from_kitsu(p) for p in raw_sequences if isinstance(p, dict)]
            cls._project_sequence_cache[project_id] = sequences

            # Also group sequences per episode cache
            seqs_by_ep: Dict[str, List[Sequence]] = {}
            for s in sequences:
                if s.episode_id:
                    seqs_by_ep.setdefault(s.episode_id, []).append(s)
            for ep_id, seq_list in seqs_by_ep.items():
                cls._sequence_cache[ep_id] = seq_list

            return sequences
        except Exception as e:
            logger.error(f"Failed to fetch sequences for project {project_id}: {e}")
            return []

    @classmethod
    def get_sequences_by_episode_id(cls, episode_id: str, use_cache: bool = True) -> List[Sequence]:
        """Fetch all sequences for an episode with optional in-memory caching."""
        if not episode_id:
            return []

        if use_cache and episode_id in cls._sequence_cache:
            return cls._sequence_cache[episode_id]

        if not is_kitsu_connected():
            return []

        try:
            raw_sequences = gazu.context.all_sequences_for_episode(episode_id) or []
            sequences = [Sequence.from_kitsu(p) for p in raw_sequences if isinstance(p, dict)]
            cls._sequence_cache[episode_id] = sequences
            return sequences
        except Exception as e:
            logger.error(f"Failed to fetch sequences for episode {episode_id}: {e}")
            return []

    @classmethod
    def _parallel_fetch_assets(cls, shots: List[Any], project_id: Optional[str] = None) -> List[List[dict]]:
        """Fetch assets for a list of shots concurrently, with graceful fallback to sequential."""
        def _fetch(s):
            sid = s.get("id", "") if isinstance(s, dict) else getattr(s, "id", "")
            pid = s.get("project_id", "") if isinstance(s, dict) else getattr(s, "project_id", project_id or "")
            if sid:
                try:
                    return cls.get_assets_for_shot(sid, project_id=pid)
                except Exception:
                    return []
            return []

        if not shots:
            return []

        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(16, max(1, len(shots)))) as executor:
                return list(executor.map(_fetch, shots))
        except (RuntimeError, Exception):
            return [_fetch(s) for s in shots]

    @classmethod
    def get_shots_by_project_id(cls, project_id: str, use_cache: bool = True) -> List[Shot]:
        """Fetch and map all shots and sequences for an entire project in bulk.

        Populates project-level and episode-level caches to make subsequent
        episode switching instantaneous (0ms).
        """
        if not project_id:
            return []

        if use_cache and project_id in cls._project_shot_cache:
            return cls._project_shot_cache[project_id]

        if not is_kitsu_connected():
            return []

        try:
            episodes = cls.get_episodes_by_project_id(project_id, use_cache=use_cache)
            ep_map: Dict[str, str] = {ep.id: ep.name for ep in episodes if ep.id}

            sequences = cls.get_sequences_by_project_id(project_id, use_cache=use_cache)
            seq_map: Dict[str, Sequence] = {seq.id: seq for seq in sequences if seq.id}

            raw_shots = gazu.shot.all_shots_for_project(project_id) or []

            mapped_shots: List[Shot] = []
            shots_by_episode: Dict[str, List[Shot]] = {ep.id: [] for ep in episodes if ep.id}

            for shot in raw_shots:
                if not isinstance(shot, dict):
                    continue

                parent_id = shot.get("parent_id", "")
                seq_obj = seq_map.get(parent_id)
                seq_name = seq_obj.name if seq_obj else ""

                ep_id = shot.get("episode_id") or (seq_obj.episode_id if seq_obj else "")
                ep_name = ep_map.get(ep_id, "")

                shot_dict = dict(shot)
                shot_dict["sequence"] = seq_name
                shot_dict["episode_id"] = ep_id
                shot_dict["episode"] = ep_name
                shot_dict["assets"] = []

                s = Shot.from_kitsu(shot_dict)
                mapped_shots.append(s)

                if ep_id in shots_by_episode:
                    shots_by_episode[ep_id].append(s)
                elif ep_id:
                    shots_by_episode[ep_id] = [s]

            # Populate episode caches
            for ep_id, ep_shots in shots_by_episode.items():
                cls._shot_cache[ep_id] = ep_shots

            cls._project_shot_cache[project_id] = mapped_shots
            return mapped_shots

        except Exception as e:
            logger.error(f"Failed to bulk fetch shots for project {project_id}: {e}")
            return []

    @classmethod
    def get_shots_by_episode_id(
        cls,
        episode_id: str,
        episode_name: str = "",
        use_cache: bool = True,
    ) -> List[Shot]:
        """Fetch and map all shots for an episode without eager asset fetching.

        Avoids the N+1 network request bottleneck by pre-mapping sequence names in O(1)
        and deferring asset fetching until action execution.
        """
        if not episode_id:
            return []

        if use_cache and episode_id in cls._shot_cache:
            return cls._shot_cache[episode_id]

        if not is_kitsu_connected():
            return []

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
                shot_dict["assets"] = []

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
        # 1. Direct sequence_id
        if sequence_id:
            if not is_kitsu_connected():
                return []
            try:
                raw_shots = gazu.shot.all_shots_for_sequence(sequence_id) or []
                mapped = []
                for s in raw_shots:
                    if isinstance(s, dict):
                        s_dict = dict(s)
                        s_dict["assets"] = []
                        mapped.append(Shot.from_kitsu(s_dict))
                return mapped
            except Exception as e:
                logger.error(f"Failed to fetch shots for sequence {sequence_id}: {e}")
                return []

        # 2. Episode ID
        if episode_id:
            all_ep_shots = cls.get_shots_by_episode_id(episode_id, episode_name=episode or "")
            if sequence:
                seq_clean = sequence.strip().lower()
                return [s for s in all_ep_shots if s.sequence and s.sequence.lower() == seq_clean]
            return all_ep_shots

        # 3. Search via episode name
        if episode and project_id:
            if project_id in cls._project_shot_cache:
                ep_clean = episode.strip().lower()
                all_ep_shots = [
                    s for s in cls._project_shot_cache[project_id]
                    if (s.episode and s.episode.lower() == ep_clean) or s.episode_id == episode
                ]
                if all_ep_shots:
                    if sequence:
                        seq_clean = sequence.strip().lower()
                        return [s for s in all_ep_shots if s.sequence and s.sequence.lower() == seq_clean]
                    return all_ep_shots

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
    def get_assets_for_shot(
        cls,
        shot_id: str,
        project_id: Optional[str] = None,
        force_refresh: bool = True,
    ) -> List[dict]:
        """Fetch assets and castings linked to a specific shot on-demand."""
        if not is_kitsu_connected() or not shot_id:
            return []

        if force_refresh:
            try:
                import gazu.cache
                gazu.cache.clear_all()
            except Exception:
                pass

        assets_by_id: Dict[str, dict] = {}

        # 1. Direct assets for shot
        try:
            raw_assets = gazu.asset.all_assets_for_shot(shot_id) or []
            for a in raw_assets:
                aid = a.get("id") if isinstance(a, dict) else getattr(a, "id", "")
                aname = a.get("name") if isinstance(a, dict) else getattr(a, "name", "")
                atype = a.get("entity_type_id") if isinstance(a, dict) else getattr(a, "entity_type_id", None)
                if aid and aname:
                    assets_by_id[aid] = {
                        "id": aid,
                        "name": aname,
                        "entity_type_id": atype,
                    }
        except Exception as e:
            logger.debug(f"gazu.asset.all_assets_for_shot failed for {shot_id}: {e}")

        # 2. Shot casting / entity links from Kitsu Casting tab
        if hasattr(gazu, "casting"):
            try:
                castings = []
                if project_id:
                    castings = gazu.casting.get_shot_casting({"id": shot_id, "project_id": project_id}) or []
                if not castings:
                    try:
                        shot_obj = gazu.shot.get_shot(shot_id)
                        p_id = shot_obj.get("project_id") if isinstance(shot_obj, dict) else getattr(shot_obj, "project_id", "")
                        if p_id:
                            castings = gazu.casting.get_shot_casting({"id": shot_id, "project_id": p_id}) or []
                    except Exception:
                        pass

                for c in castings:
                    aid = c.get("asset_id") if isinstance(c, dict) else getattr(c, "asset_id", "")
                    if aid and aid not in assets_by_id:
                        try:
                            asset_obj = gazu.asset.get_asset(aid)
                            if asset_obj:
                                aname = asset_obj.get("name") if isinstance(asset_obj, dict) else getattr(asset_obj, "name", "")
                                atype = asset_obj.get("entity_type_id") if isinstance(asset_obj, dict) else getattr(asset_obj, "entity_type_id", None)
                                if aname:
                                    assets_by_id[aid] = {
                                        "id": aid,
                                        "name": aname,
                                        "entity_type_id": atype,
                                    }
                        except Exception as ex:
                            logger.debug(f"Could not resolve cast asset {aid}: {ex}")
            except Exception as e:
                logger.debug(f"gazu.casting.get_shot_casting failed for {shot_id}: {e}")

        # 3. Asset instances
        if hasattr(gazu.shot, "get_asset_instances_for_shot"):
            try:
                instances = gazu.shot.get_asset_instances_for_shot(shot_id) or []
                for inst in instances:
                    aid = inst.get("asset_id") if isinstance(inst, dict) else getattr(inst, "asset_id", "")
                    if aid and aid not in assets_by_id:
                        try:
                            asset_obj = gazu.asset.get_asset(aid)
                            if asset_obj:
                                aname = asset_obj.get("name") if isinstance(asset_obj, dict) else getattr(asset_obj, "name", "")
                                atype = asset_obj.get("entity_type_id") if isinstance(asset_obj, dict) else getattr(asset_obj, "entity_type_id", None)
                                if aname:
                                    assets_by_id[aid] = {
                                        "id": aid,
                                        "name": aname,
                                        "entity_type_id": atype,
                                    }
                        except Exception:
                            pass
            except Exception:
                pass
        result_list = list(assets_by_id.values())
        return result_list