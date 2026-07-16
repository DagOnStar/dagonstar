# IoT providers

Providers implement capability discovery, preparation, invocation, polling, optional reattachment, and cancellation. Registration imports implementations lazily. Core installs include only deterministic `mock`, supporting all four operations, placement evidence, migration fixtures, and unknown-outcome injection. Network MQTT, WoT, and continuum adapters are not yet implemented.
