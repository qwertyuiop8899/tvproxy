import logging
import math
import time
from urllib.parse import quote, urljoin

from flask import Response

from drm.decrypter import decrypt_segment
from utils.mpd_utils import parse_mpd, parse_mpd_dict

logger = logging.getLogger(__name__)


def process_mpd_manifest(mpd_content: str, mpd_url: str, server_host: str, headers: dict = None, key_id: str = None, key: str = None) -> str:
    """
    Processes the MPD manifest and converts it to an HLS manifest.

    Args:
        mpd_content (str): The MPD manifest content.
        mpd_url (str): The URL of the MPD manifest.
        server_host (str): The server host for generating proxy URLs.
        headers (dict, optional): Headers to include in requests. Defaults to None.
        key_id (str, optional): The DRM key ID. Defaults to None.
        key (str, optional): The DRM key. Defaults to None.

    Returns:
        str: The HLS manifest as a string.
    """
    mpd_dict = parse_mpd(mpd_content)
    parsed_mpd = parse_mpd_dict(mpd_dict, mpd_url, parse_drm=True)
    
    hls_content = build_hls_from_mpd(parsed_mpd, mpd_url, server_host, headers, key_id, key)
    return hls_content


def process_mpd_playlist(mpd_content: str, mpd_url: str, profile_id: str, server_host: str, headers: dict = None, key_id: str = None, key: str = None) -> str:
    """
    Processes the MPD manifest and converts it to an HLS playlist for a specific profile.

    Args:
        mpd_content (str): The MPD manifest content.
        mpd_url (str): The URL of the MPD manifest.
        profile_id (str): The profile ID to generate the playlist for.
        server_host (str): The server host for generating proxy URLs.
        headers (dict, optional): Headers to include in requests. Defaults to None.
        key_id (str, optional): DRM key ID for segment decryption. Defaults to None.
        key (str, optional): DRM key for segment decryption. Defaults to None.

    Returns:
        str: The HLS playlist as a string.

    Raises:
        ValueError: If the profile is not found in the MPD manifest.
    """
    mpd_dict = parse_mpd(mpd_content)
    parsed_mpd = parse_mpd_dict(mpd_dict, mpd_url, parse_drm=True, parse_segment_profile_id=profile_id)
    
    matching_profiles = [p for p in parsed_mpd["profiles"] if p["id"] == profile_id]
    if not matching_profiles:
        raise ValueError("Profile not found")

    hls_content = build_hls_playlist_from_mpd(parsed_mpd, matching_profiles, mpd_url, server_host, headers, key_id, key)
    return hls_content


def process_mpd_segment(init_content: bytes, segment_content: bytes, mimetype: str, key_id: str = None, key: str = None) -> bytes:
    """
    Processes and decrypts a media segment.

    Args:
        init_content (bytes): The initialization segment content.
        segment_content (bytes): The media segment content.
        mimetype (str): The MIME type of the segment.
        key_id (str, optional): The DRM key ID. Defaults to None.
        key (str, optional): The DRM key. Defaults to None.

    Returns:
        bytes: The decrypted segment content.
    """
    logger.info(f"process_mpd_segment called with key_id={key_id}, key={key}, mimetype={mimetype}")
    logger.info(f"init_content size: {len(init_content) if init_content else 0}, segment_content size: {len(segment_content) if segment_content else 0}")
    
    if key_id and key:
        # For DRM protected content
        logger.info(f"Decrypting {mimetype} segment with ClearKey DRM")
        now = time.time()
        decrypted_content = decrypt_segment(init_content, segment_content, key_id, key)
        logger.info(f"Decryption of {mimetype} segment took {time.time() - now:.4f} seconds")
    else:
        # For non-DRM protected content, we just concatenate init and segment content
        logger.info(f"No DRM parameters provided, concatenating init + segment (key_id={key_id}, key={key})")
        decrypted_content = init_content + segment_content

    return decrypted_content


def build_hls_from_mpd(parsed_mpd: dict, mpd_url: str, server_host: str, headers: dict = None, key_id: str = None, key: str = None) -> str:
    """
    Builds an HLS manifest from the parsed MPD data.

    Args:
        parsed_mpd (dict): The parsed MPD manifest data.
        mpd_url (str): The URL of the MPD manifest.
        server_host (str): The server host for generating proxy URLs.
        headers (dict, optional): Headers to include in requests. Defaults to None.
        key_id (str, optional): The DRM key ID. Defaults to None.
        key (str, optional): The DRM key. Defaults to None.

    Returns:
        str: The HLS manifest as a string.
    """
    hls = ["#EXTM3U", "#EXT-X-VERSION:6"]
    
    video_profiles = {}
    audio_profiles = {}

    base_playlist_url = f"http://{server_host}/proxy/mpd/playlist"

    for profile in parsed_mpd["profiles"]:
        # Build URL parameters manually
        url_params = []
        url_params.append(f"mpd_url={quote(mpd_url)}")
        url_params.append(f"profile_id={profile['id']}")
        if key_id:
            url_params.append(f"key_id={key_id}")
        if key:
            url_params.append(f"key={key}")
        if headers:
            for h_key, h_value in headers.items():
                url_params.append(f"h_{quote(h_key)}={quote(h_value)}")

        playlist_url = f"{base_playlist_url}?{'&'.join(url_params)}"

        if "video" in profile["mimeType"]:
            video_profiles[profile["id"]] = (profile, playlist_url)
        elif "audio" in profile["mimeType"]:
            audio_profiles[profile["id"]] = (profile, playlist_url)

    # Add audio streams
    for i, (profile, playlist_url) in enumerate(audio_profiles.values()):
        is_default = "YES" if i == 0 else "NO"  # Set the first audio track as default
        lang = profile.get("lang", "und")
        hls.append(
            f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="{profile["id"]}",DEFAULT={is_default},AUTOSELECT={is_default},LANGUAGE="{lang}",URI="{playlist_url}"'
        )

    # Add video streams
    for profile, playlist_url in video_profiles.values():
        # Only add AUDIO attribute if there are audio profiles available
        audio_attr = ',AUDIO="audio"' if audio_profiles else ""
        width = profile.get("width", 0)
        height = profile.get("height", 0)
        hls.append(
            f'#EXT-X-STREAM-INF:BANDWIDTH={profile["bandwidth"]},RESOLUTION={width}x{height},CODECS="{profile["codecs"]}",FRAME-RATE={profile["frameRate"]}{audio_attr}'
        )
        hls.append(playlist_url)

    return "\n".join(hls)


def build_hls_playlist_from_mpd(parsed_mpd: dict, profiles: list, mpd_url: str, server_host: str, headers: dict = None, key_id: str = None, key: str = None) -> str:
    """
    Builds an HLS playlist from the parsed MPD data for specific profiles.

    Args:
        parsed_mpd (dict): The parsed MPD manifest data.
        profiles (list): The profiles to include in the playlist.
        mpd_url (str): The URL of the MPD manifest.
        server_host (str): The server host for generating proxy URLs.
        headers (dict, optional): Headers to include in requests. Defaults to None.
        key_id (str, optional): DRM key ID for segment decryption. Defaults to None.
        key (str, optional): DRM key for segment decryption. Defaults to None.

    Returns:
        str: The HLS playlist as a string.
    """
    hls = ["#EXTM3U", "#EXT-X-VERSION:6"]

    added_segments = 0

    base_segment_url = f"http://{server_host}/proxy/mpd/segment.mp4"

    for index, profile in enumerate(profiles):
        segments = profile.get("segments", [])
        if not segments:
            logger.warning(f"No segments found for profile {profile['id']}")
            continue

        # Calculate sequence for each profile independently
        first_segment = segments[0]
        extinf_values = [s.get("extinf", 3.0) for s in segments if "extinf" in s]
        target_duration = math.ceil(max(extinf_values)) if extinf_values else 3

        # Calculate media sequence using adaptive logic for different MPD types
        mpd_start_number = profile.get("segment_template_start_number", 1)
        if mpd_start_number and mpd_start_number >= 1000:
            # Amazon-style: Use absolute segment numbering but keep it reasonable for HLS
            raw_sequence = first_segment.get("number", mpd_start_number)
            # For very large sequence numbers, use modulo to keep in reasonable range
            if raw_sequence > 1000000:
                sequence = raw_sequence % 1000000
            else:
                sequence = raw_sequence
        else:
            # Sky-style: Use time-based calculation if available
            time_val = first_segment.get("time")
            duration_val = first_segment.get("duration_mpd_timescale")
            if time_val is not None and duration_val and duration_val > 0:
                calculated_sequence = math.floor(time_val / duration_val)
                # For live streams with very large sequence numbers, use modulo to keep reasonable range
                if parsed_mpd.get("isLive", False) and calculated_sequence > 100000:
                    sequence = calculated_sequence % 100000
                else:
                    sequence = calculated_sequence
            else:
                sequence = first_segment.get("number", 1)

        # Add headers for only the first profile
        if index == 0:
            hls.extend(
                [
                    f"#EXT-X-TARGETDURATION:{target_duration}",
                    f"#EXT-X-MEDIA-SEQUENCE:{sequence}",
                ]
            )
            if parsed_mpd["isLive"]:
                hls.append("#EXT-X-PLAYLIST-TYPE:EVENT")
            else:
                hls.append("#EXT-X-PLAYLIST-TYPE:VOD")

        init_url = profile.get("initUrl", "")

        for segment in segments:
            extinf = segment.get("extinf", 3.0)
            hls.append(f'#EXTINF:{extinf:.3f},')
            
            # Build segment URL parameters manually
            url_params = []
            if key_id:
                url_params.append(f"key_id={key_id}")
            if key:
                url_params.append(f"key={key}")
            url_params.append(f"init_url={quote(init_url)}")
            url_params.append(f"segment_url={quote(segment['media'])}")
            url_params.append(f"mime_type={quote(profile['mimeType'])}")
            if headers:
                for h_key, h_value in headers.items():
                    url_params.append(f"h_{quote(h_key)}={quote(h_value)}")

            segment_url = f"{base_segment_url}?{'&'.join(url_params)}"
            hls.append(segment_url)
            added_segments += 1

    if not parsed_mpd["isLive"]:
        hls.append("#EXT-X-ENDLIST")

    logger.info(f"Added {added_segments} segments to HLS playlist")
    return "\n".join(hls) + "\n"
