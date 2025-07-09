#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MPD Processor per conversione MPEG-DASH -> HLS
Adattato da MediaFlow Proxy per Flask
"""

import logging
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin, quote
from flask import Response, request

logger = logging.getLogger(__name__)

class MPDProcessor:
    """Classe per processare MPD e generare HLS"""
    
    def __init__(self, request_obj=None):
        self.logger = logging.getLogger(__name__)
        self.request = request_obj or request
    
    def process_manifest(self, mpd_dict: Dict, key_id: str = None, key: str = None) -> Response:
        """
        Converte MPD in master manifest HLS
        
        Args:
            mpd_dict: Dizionario MPD parsificato
            key_id: Key ID per DRM (opzionale)
            key: Chiave per DRM (opzionale)
            
        Returns:
            Response: Risposta Flask con manifest HLS
        """
        try:
            hls_content = self._build_master_manifest(mpd_dict, key_id, key)
            
            return Response(
                hls_content,
                mimetype='application/vnd.apple.mpegurl',
                headers={
                    'Content-Disposition': 'inline',
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                    'Access-Control-Allow-Origin': '*'
                }
            )
            
        except Exception as e:
            self.logger.error(f"Errore processo manifest: {e}")
            raise
    
    def process_playlist(self, mpd_dict: Dict, profile_id: str, key_id: str = None, key: str = None) -> Response:
        """
        Genera playlist HLS per profilo specifico
        
        Args:
            mpd_dict: Dizionario MPD parsificato
            profile_id: ID del profilo da processare
            key_id: Key ID per DRM (opzionale)
            key: Chiave per DRM (opzionale)
            
        Returns:
            Response: Risposta Flask con playlist HLS
        """
        try:
            # Trova profilo
            profile = self._find_profile_by_id(mpd_dict.get('profiles', []), profile_id)
            if not profile:
                raise ValueError(f"Profilo {profile_id} non trovato")
            
            hls_content = self._build_media_playlist(profile, mpd_dict, key_id, key)
            
            return Response(
                hls_content,
                mimetype='application/vnd.apple.mpegurl',
                headers={
                    'Content-Disposition': 'inline',
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                    'Access-Control-Allow-Origin': '*'
                }
            )
            
        except Exception as e:
            self.logger.error(f"Errore processo playlist: {e}")
            raise
    
    def _build_master_manifest(self, mpd_dict: Dict, key_id: str = None, key: str = None) -> str:
        """Costruisce master manifest HLS"""
        
        lines = ['#EXTM3U']
        lines.append('#EXT-X-VERSION:6')
        lines.append('#EXT-X-INDEPENDENT-SEGMENTS')
        
        # Ottieni profili video
        video_profiles = [p for p in mpd_dict.get('profiles', []) if p.get('type') == 'video']
        audio_profiles = [p for p in mpd_dict.get('profiles', []) if p.get('type') == 'audio']
        
        # Ordina per bandwidth
        video_profiles.sort(key=lambda p: p.get('bandwidth', 0), reverse=True)
        audio_profiles.sort(key=lambda p: p.get('bandwidth', 0), reverse=True)
        
        # Aggiungi profili audio
        for audio_profile in audio_profiles:
            lines.append(f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="{audio_profile.get("lang", "unknown")}",DEFAULT=YES,AUTOSELECT=YES,LANGUAGE="{audio_profile.get("lang", "und")}",URI="{self._build_playlist_url(audio_profile["id"], key_id, key)}"')
        
        # Aggiungi profili video
        for video_profile in video_profiles:
            bandwidth = video_profile.get('bandwidth', 0)
            width = video_profile.get('width', 0)
            height = video_profile.get('height', 0)
            codecs = video_profile.get('codecs', '')
            
            # Costruisci stringa stream info
            stream_info = f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth}'
            
            if width and height:
                stream_info += f',RESOLUTION={width}x{height}'
            
            if codecs:
                stream_info += f',CODECS="{codecs}"'
            
            if audio_profiles:
                stream_info += ',AUDIO="audio"'
            
            lines.append(stream_info)
            lines.append(self._build_playlist_url(video_profile['id'], key_id, key))
        
        # Se non ci sono profili video, usa solo audio
        if not video_profiles and audio_profiles:
            for audio_profile in audio_profiles:
                bandwidth = audio_profile.get('bandwidth', 0)
                lines.append(f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth}')
                lines.append(self._build_playlist_url(audio_profile['id'], key_id, key))
        
        return '\n'.join(lines) + '\n'
    
    def _build_media_playlist(self, profile: Dict, mpd_dict: Dict, key_id: str = None, key: str = None) -> str:
        """Costruisce playlist media HLS"""
        
        lines = ['#EXTM3U']
        lines.append('#EXT-X-VERSION:6')
        lines.append('#EXT-X-TARGETDURATION:10')
        lines.append('#EXT-X-MEDIA-SEQUENCE:0')
        lines.append('#EXT-X-PLAYLIST-TYPE:VOD')
        
        # Aggiungi mappa initialization
        if profile.get('init_url'):
            init_url = self._build_segment_url(profile['init_url'], key_id, key)
            lines.append(f'#EXT-X-MAP:URI="{init_url}"')
        
        # Aggiungi segmenti
        segments = profile.get('segments', [])
        for segment in segments:
            # Durata (default 10 secondi se non specificata)
            duration = segment.get('duration', 10000) / 1000.0  # Converti da ms a secondi
            
            lines.append(f'#EXTINF:{duration:.3f},')
            lines.append(self._build_segment_url(segment['url'], key_id, key))
        
        lines.append('#EXT-X-ENDLIST')
        
        return '\n'.join(lines) + '\n'
    
    def _build_playlist_url(self, profile_id: str, key_id: str = None, key: str = None) -> str:
        """Costruisce URL playlist per profilo"""
        
        # Ottieni parametri dalla richiesta corrente
        args = dict(self.request.args)
        args['i'] = profile_id
        
        # Aggiungi key info se fornita
        if key_id:
            args['key_id'] = key_id
        if key:
            args['key'] = key
        
        # Costruisci URL
        base_url = f"{self.request.scheme}://{self.request.host}"
        query_string = '&'.join([f"{k}={quote(str(v))}" for k, v in args.items()])
        
        return f"{base_url}/proxy/mpd/playlist.m3u8?{query_string}"
    
    def _build_segment_url(self, segment_url: str, key_id: str = None, key: str = None) -> str:
        """Costruisce URL segmento tramite proxy"""
        
        # Costruisci parametri
        params = {
            'u': segment_url,
            'mime': 'video/mp4'
        }
        
        if key_id:
            params['key_id'] = key_id
        if key:
            params['key'] = key
        
        # Ottieni parametri proxy dalla richiesta originale
        original_args = dict(self.request.args)
        for param in ['verify_ssl', 'use_request_proxy']:
            if param in original_args:
                params[param] = original_args[param]
        
        # Costruisci URL
        base_url = f"{self.request.scheme}://{self.request.host}"
        query_string = '&'.join([f"{k}={quote(str(v))}" for k, v in params.items()])
        
        return f"{base_url}/proxy/mpd/segment.mp4?{query_string}"
    
    def _find_profile_by_id(self, profiles: List[Dict], profile_id: str) -> Optional[Dict]:
        """Trova profilo per ID"""
        
        for profile in profiles:
            if profile.get('id') == profile_id:
                return profile
        
        return None

def process_segment(init_content: bytes, 
                   segment_content: bytes, 
                   key_id: str = None, 
                   key: str = None) -> Response:
    """
    Processa segmento MP4 con decriptazione opzionale
    
    Args:
        init_content: Contenuto initialization segment
        segment_content: Contenuto media segment
        key_id: Key ID per DRM (opzionale)
        key: Chiave per DRM (opzionale)
        
    Returns:
        Response: Risposta Flask con segmento
    """
    try:
        # Combina init + segment
        combined_content = init_content + segment_content
        
        # Decripta se necessario
        if key_id and key:
            from drm_decrypter import decrypt_segment
            combined_content = decrypt_segment(combined_content, key)
        
        return Response(
            combined_content,
            mimetype='video/mp4',
            headers={
                'Content-Length': str(len(combined_content)),
                'Accept-Ranges': 'bytes',
                'Access-Control-Allow-Origin': '*'
            }
        )
        
    except Exception as e:
        logger.error(f"Errore processo segmento: {e}")
        raise

def estimate_segment_duration(segments: List[Dict]) -> float:
    """
    Stima durata segmento media
    
    Args:
        segments: Lista segmenti
        
    Returns:
        float: Durata media in secondi
    """
    if not segments:
        return 10.0  # Default
    
    total_duration = 0
    valid_segments = 0
    
    for segment in segments:
        duration = segment.get('duration', 0)
        if duration > 0:
            total_duration += duration
            valid_segments += 1
    
    if valid_segments == 0:
        return 10.0
    
    # Converti da ms a secondi
    return (total_duration / valid_segments) / 1000.0

def get_target_duration(segments: List[Dict]) -> int:
    """
    Calcola target duration per HLS
    
    Args:
        segments: Lista segmenti
        
    Returns:
        int: Target duration in secondi
    """
    if not segments:
        return 10
    
    max_duration = 0
    for segment in segments:
        duration = segment.get('duration', 0)
        if duration > max_duration:
            max_duration = duration
    
    # Converti da ms a secondi e aggiungi margine
    return int((max_duration / 1000.0) + 1)

def format_duration(duration_ms: int) -> str:
    """
    Formatta durata per HLS
    
    Args:
        duration_ms: Durata in millisecondi
        
    Returns:
        str: Durata formattata
    """
    duration_sec = duration_ms / 1000.0
    return f"{duration_sec:.3f}"

def validate_profile(profile: Dict) -> bool:
    """
    Valida profilo MPD
    
    Args:
        profile: Profilo da validare
        
    Returns:
        bool: True se valido
    """
    required_fields = ['id', 'type', 'bandwidth']
    
    for field in required_fields:
        if field not in profile:
            return False
    
    # Valida tipo
    if profile['type'] not in ['video', 'audio']:
        return False
    
    # Valida segmenti o template
    if not profile.get('segments') and not profile.get('segment_template'):
        return False
    
    return True

def sort_profiles_by_quality(profiles: List[Dict]) -> List[Dict]:
    """
    Ordina profili per qualità
    
    Args:
        profiles: Lista profili
        
    Returns:
        list: Profili ordinati
    """
    return sorted(profiles, key=lambda p: p.get('bandwidth', 0), reverse=True)

def filter_supported_profiles(profiles: List[Dict]) -> List[Dict]:
    """
    Filtra profili supportati
    
    Args:
        profiles: Lista profili
        
    Returns:
        list: Profili supportati
    """
    supported = []
    
    for profile in profiles:
        if validate_profile(profile):
            supported.append(profile)
    
    return supported