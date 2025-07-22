from client import Client

data = "abc"
data_bytes = data.encode("utf-8")

client = Client("localhost:8095")

response = client.put(data_bytes, "test", is_encrypted=True)

print(response)

object_key = response["key_object"]

response = client.get(object_key)

print(response)