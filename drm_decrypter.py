#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DRM Decrypter per Clear-Key AES-CTR
Adattato da MediaFlow Proxy per Flask
"""

import logging
from typing import Optional, Tuple
from Crypto.Cipher import AES
from Crypto.Util import Counter

logger = logging.getLogger(__name__)

class DRMDecrypter:
    """Classe per la decriptazione DRM Clear-Key"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def decrypt_segment(self, 
                       segment_content: bytes, 
                       key: str, 
                       iv: str = None) -> bytes:
        """
        Decripta un segmento MP4 con Clear-Key AES-CTR
        
        Args:
            segment_content: Contenuto del segmento da decriptare
            key: Chiave AES in formato hex (32 caratteri)
            iv: Initialization Vector in hex (opzionale)
            
        Returns:
            bytes: Contenuto decriptato
        """
        try:
            if not key:
                self.logger.warning("Nessuna chiave fornita, ritorno contenuto originale")
                return segment_content
            
            # Converti chiave da hex a bytes
            if len(key) != 32:
                raise ValueError(f"Chiave deve essere 32 caratteri hex, ricevuta: {len(key)}")
            
            key_bytes = bytes.fromhex(key)
            
            # Gestisci IV
            if iv:
                if len(iv) != 32:
                    raise ValueError(f"IV deve essere 32 caratteri hex, ricevuto: {len(iv)}")
                iv_bytes = bytes.fromhex(iv)
            else:
                # IV predefinito (16 bytes di zeri)
                iv_bytes = b'\x00' * 16
            
            # Crea cipher AES-CTR
            cipher = AES.new(key_bytes, AES.MODE_CTR, nonce=iv_bytes[:8], initial_value=iv_bytes[8:])
            
            # Decripta
            decrypted_content = cipher.decrypt(segment_content)
            
            self.logger.debug(f"Segmento decriptato: {len(segment_content)} -> {len(decrypted_content)} bytes")
            return decrypted_content
            
        except Exception as e:
            self.logger.error(f"Errore nella decriptazione: {str(e)}")
            # In caso di errore, ritorna il contenuto originale
            return segment_content

def decrypt_segment(segment_content: bytes, 
                   key: str, 
                   iv: str = None) -> bytes:
    """
    Funzione di convenienza per decriptare un segmento
    
    Args:
        segment_content: Contenuto del segmento
        key: Chiave AES in hex
        iv: IV in hex (opzionale)
        
    Returns:
        bytes: Contenuto decriptato
    """
    decrypter = DRMDecrypter()
    return decrypter.decrypt_segment(segment_content, key, iv)

def validate_key_format(key: str) -> bool:
    """
    Valida formato chiave Clear-Key
    
    Args:
        key: Chiave da validare
        
    Returns:
        bool: True se valida
    """
    if not key:
        return False
    
    # Deve essere hex di 32 caratteri (128 bit)
    if len(key) != 32:
        return False
    
    try:
        int(key, 16)
        return True
    except ValueError:
        return False

def validate_key_id_format(key_id: str) -> bool:
    """
    Valida formato Key ID
    
    Args:
        key_id: Key ID da validare
        
    Returns:
        bool: True se valido
    """
    if not key_id:
        return False
    
    # Deve essere hex di 32 caratteri
    if len(key_id) != 32:
        return False
    
    try:
        int(key_id, 16)
        return True
    except ValueError:
        return False

def convert_base64_to_hex(base64_value: str) -> str:
    """
    Converte valore base64 in hex
    
    Args:
        base64_value: Valore in base64
        
    Returns:
        str: Valore in hex
    """
    import base64
    
    try:
        # Aggiungi padding se necessario
        padding = 4 - len(base64_value) % 4
        if padding != 4:
            base64_value += '=' * padding
        
        # Converti da base64 a bytes poi a hex
        decoded_bytes = base64.b64decode(base64_value)
        return decoded_bytes.hex()
    except Exception as e:
        logger.error(f"Errore conversione base64->hex: {e}")
        return base64_value

def normalize_key_format(key: str) -> str:
    """
    Normalizza formato chiave (da base64 a hex se necessario)
    
    Args:
        key: Chiave in formato base64 o hex
        
    Returns:
        str: Chiave in formato hex
    """
    if not key:
        return key
    
    # Se già in formato hex corretto, ritorna
    if validate_key_format(key):
        return key
    
    # Prova conversione da base64
    try:
        hex_key = convert_base64_to_hex(key)
        if validate_key_format(hex_key):
            return hex_key
    except:
        pass
    
    logger.warning(f"Impossibile normalizzare formato chiave: {key}")
    return key