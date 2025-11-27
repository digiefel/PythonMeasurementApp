import pandas as pd
from typing import List

class Device:
    def __init__(self, name: str, x: float, y: float):
        self.name = name
        self.x = x
        self.y = y

class Subsite:
    def __init__(self, name: str, devices: List[Device]):
        self.name = name
        self.devices = devices

class Site:
    def __init__(self, name: str, subsites: List[Subsite]):
        self.name = name
        self.subsites = subsites

def load_devices_csv(csv_path: str) -> List[Site]:
    df = pd.read_csv(csv_path)
    sites = {}
    for _, row in df.iterrows():
        site_name = row['Site']
        subsite_name = row['Subsite']
        device = Device(row['Device'], row['X'], row['Y'])
        
        if site_name not in sites:
            sites[site_name] = {}
        if subsite_name not in sites[site_name]:
            sites[site_name][subsite_name] = []
        sites[site_name][subsite_name].append(device)
    
    return [Site(name, [Subsite(sub_name, devs) for sub_name, devs in subs.items()]) for name, subs in sites.items()]