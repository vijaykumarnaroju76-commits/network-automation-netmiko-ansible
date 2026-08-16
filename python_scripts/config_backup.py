"""
Configuration Backup - Automated backup of device configurations
"""

import logging
import os
import gzip
import json
from datetime import datetime
from typing import List, Dict
from pathlib import Path
from python_scripts.device_connector import DeviceConnector

logger = logging.getLogger(__name__)


class ConfigBackup:
    """Handles automated configuration backups for network devices."""
    
    def __init__(self, backup_dir: str = './backups', retention: int = 10, compression: bool = True):
        """
        Initialize backup manager.
        
        Args:
            backup_dir: Directory to store backups
            retention: Number of backups to retain per device
            compression: Enable gzip compression
        """
        self.backup_dir = Path(backup_dir)
        self.retention = retention
        self.compression = compression
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
    def backup_device(self, connector: DeviceConnector, hostname: str) -> Dict:
        """
        Backup running and startup configurations for a device.
        
        Args:
            connector: DeviceConnector instance
            hostname: Device hostname/IP
            
        Returns:
            Dictionary with backup results
        """
        logger.info(f"Starting backup for {hostname}")
        
        # Create device backup directory
        device_backup_dir = self.backup_dir / hostname
        device_backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results = {
            'hostname': hostname,
            'timestamp': timestamp,
            'configs': {},
            'status': 'success'
        }
        
        try:
            # Backup running-config
            logger.info(f"Fetching running-config from {hostname}")
            running_config = connector.execute_command(hostname, 'show running-config')
            
            if 'ERROR' not in running_config:
                running_file = device_backup_dir / f"running_config_{timestamp}.txt"
                self._save_config(running_file, running_config)
                results['configs']['running'] = str(running_file)
                logger.info(f"Running-config backed up: {running_file}")
            
            # Backup startup-config
            logger.info(f"Fetching startup-config from {hostname}")
            startup_config = connector.execute_command(hostname, 'show startup-config')
            
            if 'ERROR' not in startup_config:
                startup_file = device_backup_dir / f"startup_config_{timestamp}.txt"
                self._save_config(startup_file, startup_config)
                results['configs']['startup'] = str(startup_file)
                logger.info(f"Startup-config backed up: {startup_file}")
            
            # Cleanup old backups
            self._cleanup_old_backups(device_backup_dir)
            
        except Exception as e:
            logger.error(f"Backup failed for {hostname}: {str(e)}")
            results['status'] = 'failed'
            results['error'] = str(e)
        
        return results
    
    def backup_all(self, devices: List[Dict]) -> Dict:
        """
        Backup all devices.
        
        Args:
            devices: List of device configurations
            
        Returns:
            Summary of all backup results
        """
        logger.info(f"Starting backup for {len(devices)} devices")
        
        with DeviceConnector(devices) as connector:
            connector.connect_all()
            
            results = {
                'timestamp': datetime.now().isoformat(),
                'devices': [],
                'summary': {
                    'total': len(devices),
                    'successful': 0,
                    'failed': 0
                }
            }
            
            for device in devices:
                hostname = device.get('host', device.get('ip'))
                
                if hostname in connector.connections:
                    backup_result = self.backup_device(connector, hostname)
                    results['devices'].append(backup_result)
                    
                    if backup_result['status'] == 'success':
                        results['summary']['successful'] += 1
                    else:
                        results['summary']['failed'] += 1
                else:
                    results['devices'].append({
                        'hostname': hostname,
                        'status': 'skipped',
                        'reason': 'Connection failed'
                    })
                    results['summary']['failed'] += 1
            
            # Save backup summary
            self._save_summary(results)
            
            return results
    
    def _save_config(self, filepath: Path, config: str) -> None:
        """
        Save configuration to file with optional compression.
        
        Args:
            filepath: Path to save config
            config: Configuration content
        """
        if self.compression:
            filepath = filepath.with_suffix('.txt.gz')
            with gzip.open(filepath, 'wt') as f:
                f.write(config)
        else:
            filepath.write_text(config)
    
    def _cleanup_old_backups(self, device_dir: Path) -> None:
        """
        Keep only the specified number of recent backups.
        
        Args:
            device_dir: Device backup directory
        """
        # Get all backup files
        pattern = '*.txt' if not self.compression else '*.gz'
        backups = sorted(device_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)
        
        # Remove old backups
        for backup in backups[self.retention:]:
            backup.unlink()
            logger.info(f"Removed old backup: {backup}")
    
    def _save_summary(self, results: Dict) -> None:
        """
        Save backup summary as JSON.
        
        Args:
            results: Backup results dictionary
        """
        summary_file = self.backup_dir / 'backup_summary.json'
        
        with open(summary_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Backup summary saved: {summary_file}")
    
    def restore_config(self, hostname: str, backup_file: str) -> bool:
        """
        Restore device configuration from backup.
        
        Args:
            hostname: Device hostname/IP
            backup_file: Path to backup file
            
        Returns:
            Success status
        """
        logger.warning(f"Restoring configuration for {hostname} from {backup_file}")
        
        # This would require careful implementation
        # For now, just log the operation
        logger.info(f"Configuration restore capability - implement with caution")
        return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Example usage
    devices = [
        {'host': '192.168.1.1', 'username': 'admin', 'password': 'pass', 'device_type': 'cisco_ios'}
    ]
    
    backup = ConfigBackup(backup_dir='./backups', retention=10)
    results = backup.backup_all(devices)
    
    print(json.dumps(results, indent=2))
