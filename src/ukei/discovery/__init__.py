"""Automated catalogue discovery with candidate-only outputs."""

from ukei.discovery.arcgis import ArcGisConnector
from ukei.discovery.base import DiscoveryCandidate, DiscoveryError, DiscoveryReport, run_discovery
from ukei.discovery.ckan import CkanConnector

__all__ = [
    "ArcGisConnector",
    "CkanConnector",
    "DiscoveryCandidate",
    "DiscoveryError",
    "DiscoveryReport",
    "run_discovery",
]
