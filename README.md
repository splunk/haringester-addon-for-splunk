# HAR Ingester Add-on for Splunk

The HAR Ingester Add-on for Splunk allows teams to ingest the HAR file data from the following solutions:

-   Splunk Observability Cloud Synthetics Browser Tests
-   Cisco Thousand Eyes Web Transactions

### Pre-requisites

#### Splunk Observability Cloud

-   Realm
-   API Token
-   Org ID (optional)

#### Cisco Thousand Eyes

-   API Token

### Overview

The HAR data file includes every first and third party resource fetched as part of a Synthetic transaction. This includes http information (status and headers), response IP address, timings, and content size and types. By breaking down the HAR file in to individual events, we can carry out deeper analysis on how a web browser loads a resource.

Additionally, we include a deep link back in to each product allowing teams to pivot back to the originating Synthetic transaction/run.

This supports use cases such as:

🔐 Security 🔐

-   create an inventory of resources - see PCI DSS requirement 6.4.3
-   monitor new resources being returned by a web page
-   geolocation of resources
-   http header analysis for security options

⚙️ IT Operations/DevOps ⚙️

-   monitor resource response times, size, and availability
-   compare resources across tests and locations
-   domain analysis
