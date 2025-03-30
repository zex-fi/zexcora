from pathlib import Path


class FileConfig:
  _location: str
  _rotation_size_in_mb: str
  _retention_time_in_week: str

  def __init__(self, location: str = 'log', rotation_size_in_mb: str = '10', retention_time_in_week: str = '1'):
    self._location = location
    self._rotation_size_in_mb = rotation_size_in_mb
    self._retention_time_in_week = retention_time_in_week

  @property
  def debug_location(self) -> str:
    return f"{self._location}/debug.log"

  @property
  def error_location(self) -> str:
    return f"{self._location}/error.log"

  @property
  def rotation(self) -> str:
    return f"{self._rotation_size_in_mb} MB"

  @property
  def retention(self) -> str:
    return f"{self._retention_time_in_week} week"

  def ensure_directory_exists(self):
    Path(self._location).mkdir(parents=True, exist_ok=True)
