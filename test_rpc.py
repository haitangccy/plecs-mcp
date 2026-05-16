import xmlrpc.client

proxy = xmlrpc.client.ServerProxy(
    "http://localhost:1080/RPC2",
    allow_none=True
)

print(proxy.system.listMethods())