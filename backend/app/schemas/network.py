import ipaddress
import re

from pydantic import BaseModel, Field, field_validator


class TracerouteRequest(BaseModel):
    target: str = Field(min_length=1, max_length=253)

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        value = value.strip().rstrip(".")
        try:
            ipaddress.IPv4Address(value)
            return value
        except ipaddress.AddressValueError:
            pass
        if not re.fullmatch(
            r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
            r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*",
            value,
        ):
            raise ValueError("Enter a valid hostname or IPv4 address.")
        return value


class SpeedTestRequest(BaseModel):
    download_bytes: int = Field(default=10_000_000, ge=100_000, le=100_000_000)
    upload_bytes: int = Field(default=5_000_000, ge=100_000, le=25_000_000)


class DiscoverDevicesRequest(BaseModel):
    max_hosts: int = Field(default=1024, ge=1, le=1024)
