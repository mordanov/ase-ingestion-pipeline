# Health Recommender with Near Real-Time Reaction, Quality Control, Reporting System, and Embedded Models

## The Customer

FunWithActivity, a global leader in health and fitness software, aims to disrupt the fitness tracker and health sensor market by launching a cutting-edge health intelligence platform. The new platform will unify data from a wide variety of fitness devices and deliver real-time, ML-personalized recommendations directly on users’ devices and cloud dashboards.

The platform will serve both B2C users and B2B partners such as gyms, resellers, and healthcare providers.

## Requirements

### Functional Requirements

*   Multi-device Support: Ingest data from a wide range of fitness trackers, smartwatches, and health sensors.
*   Real-time Personalization: Process telemetry and generate personalized recommendations (hydration, exercise, sleep) with <1 second delay.
*   Embedded ML Models: Deploy TensorFlow Lite models on devices for on-device inference.
*   Digital Twin Registration: Register phones, wearables, and sensors as digital twins in the cloud, manage metadata, and sync state.
*   Protocol Flexibility: Support multiple ingestion protocols (MQTT, HTTPS, gRPC, WebSockets, etc.).
*   Device Credits Management: Assign, track, and spend credits per device (for actions, storage, recommendations).
*   Tiered Reward System: Dynamically assign users to reward tiers (Bronze, Silver, Gold, Platinum).
*   Analytics and Dashboards: Visualize key health metrics in real-time; generate compliance and user reports.
*   Data Synchronization: Allow devices to work offline and sync up to 5–10 times per day.

### Non-Functional Requirements

*   Latency: Sub-second response time for health tips and feedback loops.
*   Scalability: Support 1M+ daily active users and up to 14.4TB/day of data.
*   Availability: 99.9% uptime, globally available cloud platform.
*   Security & Compliance: HIPAA/GDPR compliant storage, AES-256 encryption, and TLS 1.3 transport security.
*   Observability: Full tracing (OpenTelemetry), Prometheus/Grafana dashboards, structured logs.
*   Data Quality: Validation, anomaly detection, freshness checks, lineage tracking.

## Technical Considerations

*   Cloud-Native Architecture: Use of serverless and containerized components on AWS, GCP, or Azure.
*   IoT Abstraction Layer: MQTT brokers and device registries to decouple ingestion from streaming.
*   Edge ML Deployment: TFLite inference models running directly on wearable OS SDKs.
*   Data Pipeline Design: Data lake for cold storage, stream processing for real-time actions and batch processing for ML training.
*   Open-Source First: No use of proprietary third-party SaaS; open standards and libraries are most preferable.

## Expectations

*   Present a scalable, cloud-deployable architecture in a live technical session.
*   Provide a proof-of-concept (PoC) with:
    *   Device registration & ingestion
    *   ML model deployment pipeline
    *   Real-time recommendation API
    *   Simulated ingestion from sample devices
    *   Real-time dashboard
*   Be ready to live-code and answer questions about ML models, ingestion strategies, and data protection.
*   Deliver code and documentation of production-like quality.

## Data Sources and APIs Examples

*   We have a scheduled meeting with the customer people — project managers, the architect and a technical lead, where high-level architecture will be presented by you and discussed.
*   They will ask technical questions, and we expect a discussion regarding the solution details and technical implementation.
*   They have concerns around how the recommendations will be handled in the application. Please prepare a solution skeleton in your favorite programming language which:

*   have working with multiple activities/healthy tips providers, they shared with us several ones:  
    **[Service1 endpoint](https://a2da22tugdqsame4ckd3oohkmu0tnbne.lambda-url.eu-central-1.on.aws/services/service1)**  
    **[Service2 endpoint](https://a2da22tugdqsame4ckd3oohkmu0tnbne.lambda-url.eu-central-1.on.aws/services/service2)**  
    **[Swagger documentation](../docs)** providing exact format and expected protocol.
*   The exposed data model is different for each of the provider:

service1:
```json
                    input:
                        {
                            "height": 184.0, // in cm
                            "weight": 84.0, // in kg
                            "token": "service1-dev" // session token, currently use constant
                        }

                    output:
                    success
                        [
                            {
                                "confidence": 0.4, // 0..1
                                "recommendation": "Walk more" // textual recommendation
                            }, // ...
                        ]

                    error
                        {
                            "errorCode": 13, // error code
                            "errorMessage": "Invalid user data" // human-readable error message
                        }
```

service2:
```json

                    input:
                        {
                            "measurements": {
                                "mass": 184.0, // in pounds
                                "height": 6.036 // in feet
                            },
                            "birth_date": 1615876858, // unix time in UTC
                            "session_token": "123456789" // pass unique GUID for each new request
                        }

                    output:
                    success
                        {
                            "recommendations": [
                                {
                                    "priority": 750, // 1..1000 - higher - more prioritized
                                    "title": "Have more workouts per day", // short textual recommendation
                                    "details": "Workouts help improving your health." // details on recommendation
                                }, // ...
                            ]
                        }

                    error
                        {
                            "code": 13, // error code
                            "error": "Invalid user data" // human-readable error message
                        }
```    

## Solution Design and Implementation Plan

![Health Data ASE Diagram](/assets/ase-data-diagram.png)

### 1\. Device & Data Management

1.  Device onboarding with metadata (model, firmware, OS, capabilities)
2.  Twin state registry in IoT Core (AWS/GCP/Azure)
3.  SDK-based telemetry collection and file uploads via API Gateway

### 2\. IoT Event Ingestion

*   MQTT + HTTP ingestion via IoT Core or EMQX broker
*   Real-time routing with Rules Engine → processing services or data lake

### 3\. Personalization & ML

*   TFLite model training pipeline in cloud
*   Cloud-to-device model delivery
*   On-device inference + result ingestion back into platform

### 4\. Real-Time Processing

*   Stream processing for:
*   Anomaly detection
*   Reward tracking
*   Health event correlation

### 5\. Reporting & Observability

*   Prometheus/Grafana dashboards
*   User & compliance reports
*   Alerting system for abnormal readings

## Deliverables

*   Architecture diagrams (IoT-first, ML-enabled, cloud-native)
*   PoC repository with:
    *   Sample device data generator
    *   Edge ML deployment
    *   API Gateway ingestion
    *   Real-time recommendation aggregator
    
    *   Extend data aggregation: grouping by short recommendation + filter by confidence and sort by priority
    *   Extend with 3rd endpoint with different API token
    
*   Documentation:
    *   Technical architecture
    *   Deployment guide
    *   API specs
    *   ML pipeline overview
    *   Demo environment (containerized and ready to deploy)