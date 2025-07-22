import pickle
import zlib

class ObjectCompressor:
    def __init__(self, compression_level: int = 9):
        self.compression_level = compression_level

    def compress(self, obj) -> bytes:
        """Compress a Python object to a byte string."""
        pickled_data = pickle.dumps(obj)
        compressed_data = zlib.compress(pickled_data, self.compression_level)
        return compressed_data

    def decompress(self, compressed_data: bytes):
        """Decompress a byte string back to a Python object."""
        decompressed_data = zlib.decompress(compressed_data)
        obj = pickle.loads(decompressed_data)
        return obj