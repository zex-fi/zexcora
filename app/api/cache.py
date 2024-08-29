import functools
import time


def timed_lru_cache(seconds: int, maxsize: int = 1024):
    """Decorator to cache a function's return value for a specified number of seconds."""

    def decorator(func):
        cache = functools.lru_cache(maxsize=maxsize)(func)
        cache.expiration = time.time() + seconds

        @functools.wraps(func)
        def wrapped_func(*args, **kwargs):
            # Check if the cache has expired
            if time.time() >= cache.expiration:
                # Clear the cache and reset expiration time
                cache.cache_clear()
                cache.expiration = time.time() + seconds
            return cache(*args, **kwargs)

        return wrapped_func

    return decorator
