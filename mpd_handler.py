#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MPD Handler per endpoint Flask
Adattato da MediaFlow Proxy per Flask
"""

import logging
import base64
from typing import Dict, Optional
from flask import request, Response, jsonify
from urllib.parse import unquote

# Import dei moduli MPD
from mpd_utils import parse_mpd_from_url, MPDParser
from mpd_processor import MPDProcessor, process_segment
from drm_decrypter import normalize_key_format, validate_key_format, validate_key_id_format

logger = logging.getLogger(__name__)

def handle_mpd_manifest(flask_request, mpd_cache=None) -> Response:
    """
    Gestisce richiesta per manifest MPD -> HLS
    
    Args:
        flask_request: Richiesta Flask
        mpd_cache: Cache per MPD (opzionale)
        
    Returns:
        Response: Risposta Flask
    """
    try:
        # Estrai parametri
        mpd_url = flask_request.args.get('d')
        key_id = flask_request.args.get('key_id')
        key = flask_request.args.get('key')
        
        if not mpd_url:
            return jsonify({'error': 'Parametro d (MPD URL) richiesto'}), 400
        
        # Decodifica URL se necessario
        mpd_url = unquote(mpd_url)
        
        # Normalizza chiavi se fornite
        if key_id:
            key_id = normalize_key_format(key_id)
            if not validate_key_id_format(key_id):
                return jsonify({'error': 'Formato key_id non valido'}), 400
        
        if key:
            key = normalize_key_format(key)
            if not validate_key_format(key):
                return jsonify({'error': 'Formato key non valido'}), 400
        
        # Verifica cache
        cache_key = f"mpd_{mpd_url}_{key_id}_{key}"
        if mpd_cache and cache_key in mpd_cache:
            logger.debug(f"MPD trovato in cache: {cache_key}")
            mpd_dict = mpd_cache[cache_key]
        else:
            # Scarica e parsifica MPD
            logger.info(f"Scaricando MPD: {mpd_url}")
            mpd_dict = parse_mpd_from_url(mpd_url)
            
            # Salva in cache
            if mpd_cache:
                mpd_cache[cache_key] = mpd_dict
                logger.debug(f"MPD salvato in cache: {cache_key}")
        
        # Processa manifest
        processor = MPDProcessor(flask_request)
        return processor.process_manifest(mpd_dict, key_id, key)
        
    except Exception as e:
        logger.error(f"Errore handle_mpd_manifest: {str(e)}")
        return jsonify({'error': f'Errore interno del server: {str(e)}'}), 500

def handle_mpd_playlist(flask_request, mpd_cache=None) -> Response:
    """
    Gestisce richiesta per playlist MPD -> HLS
    
    Args:
        flask_request: Richiesta Flask
        mpd_cache: Cache per MPD (opzionale)
        
    Returns:
        Response: Risposta Flask
    """
    try:
        # Estrai parametri
        mpd_url = flask_request.args.get('d')
        profile_id = flask_request.args.get('i')
        key_id = flask_request.args.get('key_id')
        key = flask_request.args.get('key')
        
        if not mpd_url:
            return jsonify({'error': 'Parametro d (MPD URL) richiesto'}), 400
        
        if not profile_id:
            return jsonify({'error': 'Parametro i (profile ID) richiesto'}), 400
        
        # Decodifica URL se necessario
        mpd_url = unquote(mpd_url)
        
        # Normalizza chiavi se fornite
        if key_id:
            key_id = normalize_key_format(key_id)
        if key:
            key = normalize_key_format(key)
        
        # Verifica cache
        cache_key = f"mpd_{mpd_url}_{key_id}_{key}"
        if mpd_cache and cache_key in mpd_cache:
            logger.debug(f"MPD trovato in cache: {cache_key}")
            mpd_dict = mpd_cache[cache_key]
        else:
            # Scarica e parsifica MPD
            logger.info(f"Scaricando MPD: {mpd_url}")
            mpd_dict = parse_mpd_from_url(mpd_url)
            
            # Salva in cache
            if mpd_cache:
                mpd_cache[cache_key] = mpd_dict
        
        # Processa playlist
        processor = MPDProcessor(flask_request)
        return processor.process_playlist(mpd_dict, profile_id, key_id, key)
        
    except Exception as e:
        logger.error(f"Errore handle_mpd_playlist: {str(e)}")
        return jsonify({'error': f'Errore interno del server: {str(e)}'}), 500

def handle_mpd_segment(flask_request, segment_cache=None) -> Response:
    """
    Gestisce richiesta per segmento MPD
    
    Args:
        flask_request: Richiesta Flask
        segment_cache: Cache per segmenti (opzionale)
        
    Returns:
        Response: Risposta Flask
    """
    try:
        # Estrai parametri
        segment_url = flask_request.args.get('u')
        key_id = flask_request.args.get('key_id')
        key = flask_request.args.get('key')
        init_url = flask_request.args.get('init_url')
        
        if not segment_url:
            return jsonify({'error': 'Parametro u (segment URL) richiesto'}), 400
        
        # Decodifica URL se necessario
        segment_url = unquote(segment_url)
        if init_url:
            init_url = unquote(init_url)
        
        # Normalizza chiavi se fornite
        if key_id:
            key_id = normalize_key_format(key_id)
        if key:
            key = normalize_key_format(key)
        
        # Verifica cache segmento
        cache_key = f"segment_{segment_url}_{key_id}_{key}"
        if segment_cache and cache_key in segment_cache:
            logger.debug(f"Segmento trovato in cache: {cache_key}")
            return segment_cache[cache_key]
        
        # Scarica init segment se specificato
        init_content = b''
        if init_url:
            init_content = download_segment_content(init_url)
        
        # Scarica segment
        segment_content = download_segment_content(segment_url)
        
        # Processa segmento
        response = process_segment(init_content, segment_content, key_id, key)
        
        # Salva in cache
        if segment_cache:
            segment_cache[cache_key] = response
            logger.debug(f"Segmento salvato in cache: {cache_key}")
        
        return response
        
    except Exception as e:
        logger.error(f"Errore handle_mpd_segment: {str(e)}")
        return jsonify({'error': f'Errore interno del server: {str(e)}'}), 500

def download_segment_content(url: str) -> bytes:
    """
    Scarica contenuto segmento
    
    Args:
        url: URL del segmento
        
    Returns:
        bytes: Contenuto del segmento
    """
    import requests
    
    try:
        logger.debug(f"Scaricando segmento: {url}")
        
        # Usa la sessione globale se disponibile
        session = getattr(download_segment_content, '_session', None)
        if not session:
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            download_segment_content._session = session
        
        response = session.get(url, timeout=30)
        response.raise_for_status()
        
        logger.debug(f"Segmento scaricato: {len(response.content)} bytes")
        return response.content
        
    except Exception as e:
        logger.error(f"Errore download segmento {url}: {str(e)}")
        raise

def validate_mpd_parameters(mpd_url: str, key_id: str = None, key: str = None) -> Optional[str]:
    """
    Valida parametri MPD
    
    Args:
        mpd_url: URL MPD
        key_id: Key ID (opzionale)
        key: Chiave (opzionale)
        
    Returns:
        str: Messaggio di errore se non valido, None se valido
    """
    # Valida URL
    if not mpd_url:
        return "URL MPD richiesto"
    
    if not mpd_url.startswith(('http://', 'https://')):
        return "URL MPD deve essere HTTP/HTTPS"
    
    # Valida chiavi se fornite
    if key_id and not validate_key_id_format(key_id):
        return "Formato key_id non valido (deve essere 32 caratteri hex)"
    
    if key and not validate_key_format(key):
        return "Formato key non valido (deve essere 32 caratteri hex)"
    
    # Se una chiave è fornita, entrambe devono essere fornite
    if (key_id and not key) or (key and not key_id):
        return "key_id e key devono essere forniti insieme"
    
    return None

def extract_headers_from_request(flask_request) -> Dict[str, str]:
    """
    Estrae headers proxy dalla richiesta
    
    Args:
        flask_request: Richiesta Flask
        
    Returns:
        dict: Headers per proxy
    """
    headers = {}
    
    # Estrai headers h_*
    for key, value in flask_request.args.items():
        if key.startswith('h_'):
            header_name = key[2:].replace('_', '-')
            headers[header_name] = value
    
    # Headers di default
    if 'user-agent' not in headers:
        headers['user-agent'] = flask_request.headers.get('User-Agent', 'TVProxy/1.0')
    
    return headers

def get_proxy_settings(flask_request) -> Dict[str, bool]:
    """
    Estrae impostazioni proxy dalla richiesta
    
    Args:
        flask_request: Richiesta Flask
        
    Returns:
        dict: Impostazioni proxy
    """
    return {
        'verify_ssl': flask_request.args.get('verify_ssl', 'true').lower() == 'true',
        'use_request_proxy': flask_request.args.get('use_request_proxy', 'true').lower() == 'true'
    }

def log_request_info(flask_request, endpoint: str):
    """
    Logga informazioni richiesta
    
    Args:
        flask_request: Richiesta Flask
        endpoint: Nome endpoint
    """
    logger.info(f"[{endpoint}] {flask_request.method} {flask_request.url}")
    logger.debug(f"[{endpoint}] Headers: {dict(flask_request.headers)}")
    logger.debug(f"[{endpoint}] Args: {dict(flask_request.args)}")

def create_error_response(message: str, status_code: int = 500) -> Response:
    """
    Crea risposta di errore
    
    Args:
        message: Messaggio di errore
        status_code: Codice stato HTTP
        
    Returns:
        Response: Risposta Flask
    """
    return jsonify({
        'error': message,
        'status_code': status_code
    }), status_code

def parse_base64_key(key_b64: str) -> str:
    """
    Parsifica chiave da base64 a hex
    
    Args:
        key_b64: Chiave in base64
        
    Returns:
        str: Chiave in hex
    """
    try:
        # Aggiungi padding se necessario
        padding = 4 - len(key_b64) % 4
        if padding != 4:
            key_b64 += '=' * padding
        
        # Decodifica e converti in hex
        key_bytes = base64.b64decode(key_b64)
        return key_bytes.hex()
        
    except Exception as e:
        logger.error(f"Errore parsing base64 key: {e}")
        raise ValueError(f"Chiave base64 non valida: {key_b64}")

def get_content_type_from_url(url: str) -> str:
    """
    Determina content type da URL
    
    Args:
        url: URL del contenuto
        
    Returns:
        str: Content type
    """
    if url.endswith('.mp4'):
        return 'video/mp4'
    elif url.endswith('.m4s'):
        return 'video/mp4'
    elif url.endswith('.m4a'):
        return 'audio/mp4'
    elif url.endswith('.webm'):
        return 'video/webm'
    else:
        return 'application/octet-stream'

# Configurazione logging per debug
def setup_mpd_logging():
    """Configura logging per moduli MPD"""
    
    # Configura logger root se non già fatto
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
    
    # Configura logger specifici
    for module_name in ['mpd_utils', 'mpd_processor', 'drm_decrypter', 'mpd_handler']:
        logger = logging.getLogger(module_name)
        logger.setLevel(logging.DEBUG)

# Inizializza logging
setup_mpd_logging()