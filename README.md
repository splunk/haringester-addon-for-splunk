# HAR Ingester Add-on for Splunk

The HAR Ingester Add-on for Splunk allows teams to ingest the HAR file data from the following solutions:

-   Splunk Observability Cloud Synthetics Browser Tests
-   Thousand Eyes Web Transactions

### Pre-requisites

#### Splunk Observability Cloud

-   Realm
-   API Token
-   Org ID (optional)

#### Thousand Eyes

-   API Token

### Overview

The HAR data includes each first and third party resource fetched as part of a Synthetic transaction and includes http information (status and headers), response IP address, timings and content size.

This supports use cases such as:

Security - creating an inventory of resources, monitoring for new resources being returned by a web page, geolocation of resources, and security header options.

IT Operations/DevOps - monitoring resources response times, size, and availability.
