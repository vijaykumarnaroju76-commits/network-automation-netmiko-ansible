"""
Device Connector - Manages connections to multiple Cisco devices using Netmiko
"""

import logging
from typing import List, Dict, Tuple
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
import concurrent.futures
import time

logger = logging.getLogger(__name__)


class DeviceConnector:
    """Manages connections to multiple network devices."""
    
    def __init__(self, devices: List[Dict], timeout: int = 30, retries: int = 3):
        """
        Initialize device connector.
        
        Args:
            devices: List of device dictionaries with host, username, password, device_type
            timeout: Connection timeout in seconds
            retries: Number of retry attempts
        """
        self.devices = devices
        self.timeout = timeout
        self.retries = retries
        self.connections = {}
        self.failed_devices = []
        
    def connect_to_device(self, device: Dict) -> Tuple[str, bool, str]:
        """
        Connect to a single device with retry logic.
        
        Args:
            device: Device configuration dictionary
            
        Returns:
            Tuple of (hostname, success, message)
        """
        hostname = device.get('host', device.get('ip'))
        
        for attempt in range(self.retries):
            try:
                logger.info(f"Attempting connection to {hostname} (attempt {attempt + 1}/{self.retries})")
                
                device_config = {
                    'host': hostname,
                    'username': device['username'],
                    'password': device['password'],
                    'device_type': device.get('device_type', 'cisco_ios'),
                    'timeout': self.timeout,
                    'auth_timeout': self.timeout,
                    'read_timeout': self.timeout,
                }
                
                # Add secret (enable password) if provided
                if 'secret' in device:
                    device_config['secret'] = device['secret']
                
                # Connect
                net_connect = ConnectHandler(**device_config)
                self.connections[hostname] = net_connect
                
                logger.info(f"Successfully connected to {hostname}")
                return (hostname, True, "Connected successfully")
                
            except NetmikoAuthenticationException as e:
                logger.error(f"Authentication failed for {hostname}: {str(e)}")
                return (hostname, False, f"Authentication failed: {str(e)}")
                
            except NetmikoTimeoutException as e:
                logger.warning(f"Timeout on attempt {attempt + 1} for {hostname}")
                if attempt == self.retries - 1:
                    logger.error(f"Connection timeout for {hostname} after {self.retries} attempts")
                    return (hostname, False, f"Connection timeout")
                time.sleep(2 ** attempt)  # Exponential backoff
                
            except Exception as e:
                logger.error(f"Connection error for {hostname}: {str(e)}")
                return (hostname, False, f"Connection error: {str(e)}")
        
        self.failed_devices.append(hostname)
        return (hostname, False, "Connection failed after retries")
    
    def connect_all(self) -> Dict[str, bool]:
        """
        Connect to all devices in parallel.
        
        Returns:
            Dictionary of device status (hostname: success)
        """
        results = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.connect_to_device, device): device 
                      for device in self.devices}
            
            for future in concurrent.futures.as_completed(futures):
                hostname, success, message = future.result()
                results[hostname] = success
                logger.info(f"{hostname}: {message}")
        
        return results
    
    def execute_command(self, hostname: str, command: str) -> str:
        """
        Execute a single command on a device.
        
        Args:
            hostname: Device hostname/IP
            command: Command to execute
            
        Returns:
            Command output
        """
        if hostname not in self.connections:
            logger.error(f"No connection to {hostname}")
            return f"ERROR: No connection to {hostname}"
        
        try:
            output = self.connections[hostname].send_command(command)
            logger.debug(f"Executed '{command}' on {hostname}")
            return output
        
        except Exception as e:
            logger.error(f"Error executing command on {hostname}: {str(e)}")
            return f"ERROR: {str(e)}"
    
    def execute_commands(self, commands: List[str], hostname: str = None) -> Dict:
        """
        Execute multiple commands on one or all devices.
        
        Args:
            commands: List of commands to execute
            hostname: Optional specific device, if None execute on all
            
        Returns:
            Dictionary of results by device
        """
        results = {}
        
        if hostname:
            results[hostname] = {}
            for cmd in commands:
                results[hostname][cmd] = self.execute_command(hostname, cmd)
        else:
            for device_hostname in self.connections.keys():
                results[device_hostname] = {}
                for cmd in commands:
                    results[device_hostname][cmd] = self.execute_command(device_hostname, cmd)
        
        return results
    
    def execute_config_commands(self, hostname: str, commands: List[str]) -> Tuple[bool, str]:
        """
        Execute configuration commands on a device.
        
        Args:
            hostname: Device hostname/IP
            commands: List of configuration commands
            
        Returns:
            Tuple of (success, output)
        """
        if hostname not in self.connections:
            logger.error(f"No connection to {hostname}")
            return (False, f"No connection to {hostname}")
        
        try:
            output = self.connections[hostname].send_config_set(commands)
            logger.info(f"Configuration commands sent to {hostname}")
            return (True, output)
        
        except Exception as e:
            logger.error(f"Configuration error on {hostname}: {str(e)}")
            return (False, str(e))
    
    def save_config(self, hostname: str) -> Tuple[bool, str]:
        """
        Save running configuration to startup config.
        
        Args:
            hostname: Device hostname/IP
            
        Returns:
            Tuple of (success, message)
        """
        if hostname not in self.connections:
            return (False, f"No connection to {hostname}")
        
        try:
            output = self.connections[hostname].send_command("write memory")
            logger.info(f"Configuration saved on {hostname}")
            return (True, output)
        
        except Exception as e:
            logger.error(f"Error saving config on {hostname}: {str(e)}")
            return (False, str(e))
    
    def disconnect(self, hostname: str = None) -> None:
        """
        Disconnect from device(s).
        
        Args:
            hostname: Optional specific device, if None disconnect all
        """
        if hostname:
            if hostname in self.connections:
                self.connections[hostname].disconnect()
                del self.connections[hostname]
                logger.info(f"Disconnected from {hostname}")
        else:
            for host in list(self.connections.keys()):
                self.connections[host].disconnect()
                del self.connections[host]
            logger.info("Disconnected from all devices")
    
    def get_connection_status(self) -> Dict:
        """
        Get status of all connections.
        
        Returns:
            Dictionary of connection status
        """
        return {
            'connected': list(self.connections.keys()),
            'failed': self.failed_devices,
            'total': len(self.devices),
            'success_rate': f"{len(self.connections) / len(self.devices) * 100:.1f}%"
        }
    
    def __enter__(self):
        """Context manager entry."""
        self.connect_all()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


if __name__ == '__main__':
    # Example usage
    import os
    
    devices = [
        {
            'host': os.getenv('DEVICE1_IP', '192.168.1.1'),
            'username': os.getenv('NETWORK_USER', 'admin'),
            'password': os.getenv('NETWORK_PASS', 'password'),
            'device_type': 'cisco_ios'
        }
    ]
    
    with DeviceConnector(devices) as connector:
        results = connector.execute_commands(['show version', 'show ip int brief'])
        for device, cmds in results.items():
            print(f"\n{device}:")
            for cmd, output in cmds.items():
                print(f"  {cmd}:")
                print(f"    {output}")
