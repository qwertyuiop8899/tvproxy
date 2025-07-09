#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MPD Utils per parsing manifesti MPEG-DASH
Adattato da MediaFlow Proxy per Flask
"""

import logging
import re
import base64
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

# Prova import xmltodict
try:
    import xmltodict
    XML_AVAILABLE = True
except ImportError:
    XML_AVAILABLE = False
    logger.warning("xmltodict non disponibile, parsing MPD disabilitato")

class MPDParser:
    """Classe per il parsing di manifesti MPD"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse_mpd_content(self, mpd_content: str, base_url: str = None) -> Dict[str, Any]:
        """
        Parsifica contenuto MPD XML
        
        Args:
            mpd_content: Contenuto XML dell'MPD
            base_url: URL base per risolvere URL relativi
            
        Returns:
            dict: Dizionario con dati MPD parsificati
        """
        if not XML_AVAILABLE:
            raise ImportError("xmltodict richiesto per parsing MPD")
        
        try:
            # Parsing XML
            mpd_dict = xmltodict.parse(mpd_content)
            
            # Estrai informazioni principali
            mpd_root = mpd_dict.get('MPD', {})
            
            # Informazioni base
            result = {
                'type': mpd_root.get('@type', 'static'),
                'duration': self._parse_duration(mpd_root.get('@mediaPresentationDuration')),
                'profiles': [],
                'drmInfo': {'isDrmProtected': False},
                'baseUrl': base_url or ''
            }
            
            # Parsifica periods
            periods = mpd_root.get('Period', [])
            if not isinstance(periods, list):
                periods = [periods]
            
            for period in periods:
                self._parse_period(period, result, base_url)
            
            # Cerca informazioni DRM
            drm_info = self._extract_drm_info(mpd_root)
            if drm_info:
                result['drmInfo'] = drm_info
            
            return result
            
        except Exception as e:
            self.logger.error(f"Errore parsing MPD: {e}")
            raise
    
    def _parse_period(self, period: Dict, result: Dict, base_url: str):
        """Parsifica un Period MPD"""
        
        adaptation_sets = period.get('AdaptationSet', [])
        if not isinstance(adaptation_sets, list):
            adaptation_sets = [adaptation_sets]
        
        for adaptation_set in adaptation_sets:
            self._parse_adaptation_set(adaptation_set, result, base_url)
    
    def _parse_adaptation_set(self, adaptation_set: Dict, result: Dict, base_url: str):
        """Parsifica un AdaptationSet"""
        
        content_type = adaptation_set.get('@contentType', 'unknown')
        mime_type = adaptation_set.get('@mimeType', '')
        
        # Determina tipo media
        if content_type == 'video' or 'video' in mime_type:
            media_type = 'video'
        elif content_type == 'audio' or 'audio' in mime_type:
            media_type = 'audio'
        else:
            media_type = 'unknown'
        
        # Parsifica representations
        representations = adaptation_set.get('Representation', [])
        if not isinstance(representations, list):
            representations = [representations]
        
        for representation in representations:
            profile = self._parse_representation(representation, media_type, base_url)
            if profile:
                result['profiles'].append(profile)
    
    def _parse_representation(self, representation: Dict, media_type: str, base_url: str) -> Dict:
        """Parsifica una Representation"""
        
        rep_id = representation.get('@id', '')
        bandwidth = int(representation.get('@bandwidth', 0))
        
        profile = {
            'id': rep_id,
            'type': media_type,
            'bandwidth': bandwidth,
            'codecs': representation.get('@codecs', ''),
            'init_url': '',
            'segment_template': '',
            'segments': []
        }
        
        # Risoluzione per video
        if media_type == 'video':
            profile['width'] = int(representation.get('@width', 0))
            profile['height'] = int(representation.get('@height', 0))
            profile['frameRate'] = representation.get('@frameRate', '25')
        
        # Informazioni audio
        if media_type == 'audio':
            profile['audioSampleRate'] = int(representation.get('@audioSampleRate', 48000))
            profile['lang'] = representation.get('@lang', 'und')
        
        # Parsifica SegmentTemplate
        segment_template = representation.get('SegmentTemplate', {})
        if segment_template:
            self._parse_segment_template(segment_template, profile, base_url)
        
        # Parsifica SegmentList
        segment_list = representation.get('SegmentList', {})
        if segment_list:
            self._parse_segment_list(segment_list, profile, base_url)
        
        return profile
    
    def _parse_segment_template(self, segment_template: Dict, profile: Dict, base_url: str):
        """Parsifica SegmentTemplate"""
        
        # URL template
        media_template = segment_template.get('@media', '')
        init_template = segment_template.get('@initialization', '')
        
        profile['segment_template'] = media_template
        profile['init_url'] = self._resolve_url(init_template, base_url)
        
        # Timeline
        timeline = segment_template.get('SegmentTimeline', {})
        if timeline:
            segments = timeline.get('S', [])
            if not isinstance(segments, list):
                segments = [segments]
            
            current_time = 0
            timescale = int(segment_template.get('@timescale', 1000))
            
            for i, segment in enumerate(segments):
                duration = int(segment.get('@d', 0))
                repeat = int(segment.get('@r', 0))
                
                # Aggiungi segmento base
                profile['segments'].append({
                    'number': i + 1,
                    'time': current_time,
                    'duration': duration,
                    'url': self._build_segment_url(media_template, i + 1, current_time, base_url)
                })
                
                current_time += duration
                
                # Aggiungi ripetizioni
                for r in range(repeat):
                    profile['segments'].append({
                        'number': i + 1 + r + 1,
                        'time': current_time,
                        'duration': duration,
                        'url': self._build_segment_url(media_template, i + 1 + r + 1, current_time, base_url)
                    })
                    current_time += duration
    
    def _parse_segment_list(self, segment_list: Dict, profile: Dict, base_url: str):
        """Parsifica SegmentList"""
        
        # Initialization
        init_segment = segment_list.get('Initialization', {})
        if init_segment:
            profile['init_url'] = self._resolve_url(init_segment.get('@sourceURL', ''), base_url)
        
        # Segments
        segments = segment_list.get('SegmentURL', [])
        if not isinstance(segments, list):
            segments = [segments]
        
        for i, segment in enumerate(segments):
            media_url = segment.get('@media', '')
            profile['segments'].append({
                'number': i + 1,
                'time': 0,  # Non disponibile in SegmentList
                'duration': 0,  # Non disponibile in SegmentList
                'url': self._resolve_url(media_url, base_url)
            })
    
    def _build_segment_url(self, template: str, number: int, time: int, base_url: str) -> str:
        """Costruisce URL segmento da template"""
        
        url = template.replace('$Number$', str(number))
        url = url.replace('$Time$', str(time))
        
        return self._resolve_url(url, base_url)
    
    def _resolve_url(self, url: str, base_url: str) -> str:
        """Risolve URL relativo"""
        
        if not url or not base_url:
            return url
        
        # Se URL è già assoluto, ritorna
        if url.startswith('http'):
            return url
        
        # Risolvi URL relativo
        return urljoin(base_url, url)
    
    def _extract_drm_info(self, mpd_root: Dict) -> Optional[Dict]:
        """Estrae informazioni DRM dall'MPD"""
        
        # Cerca ContentProtection
        content_protection = self._find_content_protection(mpd_root)
        if not content_protection:
            return None
        
        drm_info = {
            'isDrmProtected': True,
            'drmSystem': 'clearkey',
            'keyId': None,
            'key': None
        }
        
        # Cerca Clear Key
        for cp in content_protection:
            scheme_id = cp.get('@schemeIdUri', '')
            if 'clearkey' in scheme_id.lower():
                # Cerca Key ID
                key_id = cp.get('@value')
                if key_id:
                    drm_info['keyId'] = key_id
                
                # Cerca chiave in elementi figli
                key_element = cp.get('clearkey:Laurl')
                if key_element:
                    drm_info['laUrl'] = key_element
        
        return drm_info
    
    def _find_content_protection(self, node: Dict) -> List[Dict]:
        """Trova elementi ContentProtection ricorsivamente"""
        
        result = []
        
        if isinstance(node, dict):
            # Cerca ContentProtection in questo nodo
            cp = node.get('ContentProtection')
            if cp:
                if isinstance(cp, list):
                    result.extend(cp)
                else:
                    result.append(cp)
            
            # Ricerca ricorsiva
            for value in node.values():
                result.extend(self._find_content_protection(value))
        
        elif isinstance(node, list):
            for item in node:
                result.extend(self._find_content_protection(item))
        
        return result
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parsifica durata ISO 8601"""
        
        if not duration_str:
            return 0
        
        # Regex per PT1H23M45S
        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?'
        match = re.match(pattern, duration_str)
        
        if not match:
            return 0
        
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = float(match.group(3) or 0)
        
        return int(hours * 3600 + minutes * 60 + seconds)

def parse_mpd_from_url(url: str, session=None) -> Dict[str, Any]:
    """
    Scarica e parsifica MPD da URL
    
    Args:
        url: URL dell'MPD
        session: Sessione requests (opzionale)
        
    Returns:
        dict: Dati MPD parsificati
    """
    import requests
    
    if not session:
        session = requests.Session()
    
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        
        parser = MPDParser()
        return parser.parse_mpd_content(response.text, url)
        
    except Exception as e:
        logger.error(f"Errore download/parsing MPD {url}: {e}")
        raise

def extract_clear_key_info(mpd_dict: Dict) -> Dict[str, str]:
    """
    Estrae informazioni Clear-Key dall'MPD
    
    Args:
        mpd_dict: Dizionario MPD parsificato
        
    Returns:
        dict: Informazioni Clear-Key
    """
    drm_info = mpd_dict.get('drmInfo', {})
    
    if not drm_info.get('isDrmProtected'):
        return {}
    
    return {
        'keyId': drm_info.get('keyId'),
        'key': drm_info.get('key'),
        'laUrl': drm_info.get('laUrl')
    }

def filter_profiles_by_type(profiles: List[Dict], media_type: str) -> List[Dict]:
    """
    Filtra profili per tipo media
    
    Args:
        profiles: Lista profili
        media_type: Tipo media (video/audio)
        
    Returns:
        list: Profili filtrati
    """
    return [p for p in profiles if p.get('type') == media_type]

def get_best_video_profile(profiles: List[Dict]) -> Optional[Dict]:
    """
    Ottiene il miglior profilo video
    
    Args:
        profiles: Lista profili
        
    Returns:
        dict: Miglior profilo video
    """
    video_profiles = filter_profiles_by_type(profiles, 'video')
    
    if not video_profiles:
        return None
    
    # Ordina per bandwidth decrescente
    video_profiles.sort(key=lambda p: p.get('bandwidth', 0), reverse=True)
    
    return video_profiles[0]

def get_best_audio_profile(profiles: List[Dict]) -> Optional[Dict]:
    """
    Ottiene il miglior profilo audio
    
    Args:
        profiles: Lista profili
        
    Returns:
        dict: Miglior profilo audio
    """
    audio_profiles = filter_profiles_by_type(profiles, 'audio')
    
    if not audio_profiles:
        return None
    
    # Ordina per bandwidth decrescente
    audio_profiles.sort(key=lambda p: p.get('bandwidth', 0), reverse=True)
    
    return audio_profiles[0]