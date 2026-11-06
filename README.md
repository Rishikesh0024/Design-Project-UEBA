# User and Entity Behaviour Analytics (UEBA) for Internal Threat Identification

<p align="center">
  <strong>An AI-Assisted Cybersecurity Platform for Behavioural Analysis and Threat Identification</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Domain-Cybersecurity-blue" />
  <img src="https://img.shields.io/badge/Focus-UEBA-red" />
  <img src="https://img.shields.io/badge/AI-Machine%20Learning-purple" />
  <img src="https://img.shields.io/badge/Project-Design%20Project%20I-green" />
</p>

## 1. Project Overview

Organizations generate large volumes of digital activity data through employee logins, file access, email communication, web browsing, and removable storage devices. Analysing these activities manually is difficult, especially in environments with large numbers of users and interconnected resources.

One of the major cybersecurity challenges is identifying potentially malicious activities performed through authorized access. Such activities may initially appear similar to normal user behaviour, making them difficult to identify using traditional security monitoring approaches.

**User and Entity Behaviour Analytics (UEBA) for Internal Threat Identification** is a cybersecurity project that aims to analyse user and entity activities, establish behavioural profiles, identify unusual patterns, calculate risk scores, and generate prioritised security alerts.

The project explores the integration of temporal analysis, graph-based relationship analysis, and statistical behavioural profiling to support more contextual and explainable threat identification.

## 2. Project Objectives

The main objectives are:

- Collect and preprocess user activity records from security datasets.
- Establish individual and role-based behavioural profiles.
- Analyse temporal patterns and relationships between users and resources.
- Identify unusual activities using behavioural anomaly detection.
- Combine multiple anomaly indicators into an overall risk score.
- Prioritise potential threats using role-aware thresholds.
- Generate security alerts with supporting evidence and reason codes.
- Evaluate detection performance using appropriate metrics.

## 3. Key Features

The UEBA platform is organised into seven primary modules.

### 3.1 Dashboard

Provides an overview of the platform, including:

- Dataset statistics
- Total activity records
- User and entity information
- Activity distribution
- Risk distribution
- Recent security events
- Detection summaries

### 3.2 Dataset Upload

Provides functionality for importing and managing activity datasets.

Features include:

- CSV dataset upload
- CERT-style activity dataset support
- Custom CSV schema handling
- Activity and role metadata processing
- Column alias detection
- Data validation and preprocessing
- Dataset quality reporting
- Reproducible synthetic demonstration datasets

### 3.3 Activity Explorer

Allows users to examine processed activity records.

Features include:

- Activity record exploration
- User-based filtering
- Event category filtering
- Timestamp-based search
- Event ID inspection
- Activity details and historical records

### 3.4 Behaviour Profiles

Analyses individual and role-based behavioural patterns.

Features include:

- User activity summaries
- Role-based behavioural context
- Historical activity comparison
- Behavioural deviation analysis
- Identification of unusual activity patterns

### 3.5 Anomaly Detection

Provides behavioural analysis and anomaly identification.

The research design explores three analytical branches:

- Temporal sequence analysis
- User-resource relationship analysis
- Personal and peer behavioural analysis

The resulting anomaly indicators are intended to support combined risk assessment.

### 3.6 Alerts

Displays prioritised security alerts based on available risk scores.

Features include:

- Ranked security alerts
- Risk severity classification
- Combined risk score
- Individual anomaly scores
- Detection reasons
- Related event evidence
- Alert investigation
- Analyst review and status tracking

### 3.7 Evaluation

Provides an evaluation workspace for analysing available model results.

Potential evaluation measures include:

- Precision
- Recall
- F1-score
- PR-AUC
- ROC-AUC
- False Positive Rate (FPR)
- Top-K Precision
- Detection Delay
- Alert Volume
- Processing Time

Evaluation charts and metrics should be generated from actual completed experiments and test-set predictions.

## 4. Proposed Research Architecture

The proposed research architecture consists of multiple analytical and monitoring components.

### 4.1 Temporal Branch – Causal Transformer

The temporal branch analyses sequences of user activities and predicts the next likely event.

It produces a sequence-surprise score based on differences between expected and observed activities.

### 4.2 Relational Branch – Heterogeneous Graph Transformer (HGT)

The relational branch models interactions between users, devices, resources, and other entities using a heterogeneous graph.

The HGT and relation decoder are proposed to identify unusual relationships and generate interaction-surprise scores.

### 4.3 Personal and Peer Context

This component uses:

- Rolling Median
- Median Absolute Deviation (MAD)
- Individual behavioural baselines
- Role-based peer comparisons

It identifies deviations between current activity and historical behavioural patterns.

### 4.4 Score Fusion

The anomaly scores from the three branches are intended to be calibrated using calibration-set percentiles and combined through a weighted mean.

The resulting score represents the overall behavioural risk.

### 4.5 ADWIN Drift Monitoring

Adaptive Windowing (ADWIN) is proposed to monitor changes in anomaly-score distributions and identify potential behavioural drift.

### 4.6 Role-Aware Thresholds

Rolling empirical quantiles are used in the proposed design to establish role-aware alert thresholds, with a global fallback when sufficient role-specific information is unavailable.

### 4.7 Controlled Update Gate

The proposed update mechanism allows baseline or threshold updates only using activities reviewed and confirmed as benign by analysts.

### 4.8 Ranked Alerts and Evidence

The system is designed to produce prioritised alerts containing:

- User or entity information
- Related event IDs
- Individual branch scores
- Combined risk score
- Detection reason codes
- Supporting activity evidence
- Analyst review information

### Architecture Workflow

```text
             CERT ACTIVITY DATA
       Logon | File | Email | Web | USB
                    |
                    v
             DATA PREPROCESSING
                    |
          +---------+---------+
          |         |         |
          v         v         v
       TEMPORAL  RELATIONAL  PERSONAL / PEER
       BRANCH    BRANCH      CONTEXT
          |         |         |
       Causal      HGT      Rolling Median
     Transformer            + MAD
          |         |         |
          +---------+---------+
                    |
                    v
                SCORE FUSION
          Calibration + Weighted Mean
                    |
                    v
              DRIFT MONITORING
                  ADWIN
                    |
                    v
            ROLE-AWARE THRESHOLDS
                    |
                    v
              CONTROLLED UPDATE
                    |
                    v
             RANKED SECURITY ALERTS
                    |
                    v
              EVIDENCE & REVIEW
```

**Implementation status:** The current prototype includes empirical temporal transition surprise, historical user-resource edge novelty, and user/role median-and-MAD contextual scoring. The Causal Transformer, HGT relation decoder, ADWIN drift detector, and controlled threshold-update mechanism are proposed research components and should be marked implemented only after development and testing.

## 5. Dataset

The project uses the **CERT Insider Threat Dataset** as its intended benchmark for behavioural analysis and threat identification.

The dataset contains different categories of user activity:

| Activity Category | Description |
|---|---|
| Logon / Logoff | User authentication and session activity |
| File Activity | File access and modification |
| Email Activity | User email communication |
| Web Activity | Website access and browsing |
| Removable Devices | USB and external storage activity |
| Role Metadata | User roles and organisational information |

The platform also supports synthetic demonstration datasets for exploring the workflow.

Synthetic demonstrations are not genuine CERT records and must be identified separately from benchmark data.

## 6. Technology Stack

| Component | Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Data Processing | Pandas, NumPy |
| Machine Learning | Scikit-learn |
| Deep Learning | PyTorch |
| Graph Learning | PyTorch Geometric |
| Visualisation | Interactive charts and graph visualisations |
| Dataset Format | CSV |
| API Documentation | FastAPI Swagger UI |
| Version Control | Git and GitHub |

## 7. System Architecture

The platform follows a frontend-backend architecture.

**Frontend:** Provides the user interface for dataset management, activity exploration, behavioural analysis, alerts, and evaluation.

**Backend:** Handles API requests, dataset processing, behavioural scoring, anomaly detection, and alert generation.

**Database:** PostgreSQL stores application data, datasets, processed events, behavioural information, and other supported records.

```text
                  USER
                   |
                   v
             REACT FRONTEND
                   |
                   v
              FASTAPI BACKEND
                   |
         +---------+----------+
         |         |          |
         v         v          v
      DATASET   BEHAVIOUR   DETECTION
      PROCESS   ANALYSIS    ENGINE
         |         |          |
         +---------+----------+
                   |
                   v
              POSTGRESQL
                   |
         +---------+----------+
         |                    |
         v                    v
    RISK SCORING          EVALUATION
         |
         v
    SECURITY ALERTS
```

## 8. Installation and Setup

### Prerequisites

Install the following before running the project:

- Python 3.11 or later
- Node.js and npm
- PostgreSQL
- Git
- Visual Studio Code (recommended)

### Step 1: Clone the Repository

```bash
git clone https://github.com/Rishikesh0024/Design-Project-UEBA.git
cd Design-Project-UEBA
```

### Step 2: Backend Setup

Navigate to the backend directory:

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate the environment.

**macOS / Linux:**

```bash
source .venv/bin/activate
```

**Windows:**

```bash
.venv\Scripts\activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Configure the environment variables using the provided `.env.example`, if available. Set the PostgreSQL connection details and required application secrets.

If the project uses Alembic migrations, apply them:

```bash
alembic upgrade head
```

Start the backend using the configured FastAPI application entry point. For example:

```bash
uvicorn app.main:app --reload
```

Backend address:

`http://localhost:8000`

API documentation:

`http://localhost:8000/docs`

### Step 3: Frontend Setup

Open another terminal and navigate to the frontend directory:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

Open the local application address displayed in the terminal, commonly:

`http://localhost:5173`

**Note:** The commands and application entry points above assume the corresponding directories, scripts, configuration files, and modules exist in the repository. Follow the actual project configuration if names differ.

## 9. Evaluation Methodology

The project considers the following evaluation metrics:

| Metric | Purpose |
|---|---|
| Precision | Measures the proportion of flagged activities that are actually suspicious |
| Recall | Measures the proportion of suspicious activities detected |
| F1-score | Balances precision and recall |
| PR-AUC | Evaluates precision-recall performance |
| ROC-AUC | Measures discrimination across classification thresholds |
| False Positive Rate | Measures the proportion of normal activities incorrectly flagged |
| Top-K Precision | Measures the quality of the highest-ranked alerts |
| Detection Delay | Measures the time taken to identify suspicious activity |
| Alert Volume | Measures the number of alerts generated |
| Processing Time | Measures computational performance |

Experiments should use chronological data partitioning and prevent future-event leakage. Ground-truth labels must be excluded from the scoring process and used only for evaluation.

No experimental performance values are claimed in this documentation unless supported by completed experiments.

## 10. Research Novelty

The proposed research explores the following aspects:

1. **Multi-Approach Behaviour Analysis:** Combining temporal, relational, and statistical behavioural analysis.
2. **Personalised Behaviour Monitoring:** Comparing individual behaviour with historical and role-based patterns.
3. **Combined Anomaly Scoring:** Integrating multiple anomaly indicators into an overall risk score.
4. **Role-Aware Threat Identification:** Considering differences in expected activities across organisational roles.
5. **Evidence-Based Alerts:** Providing supporting events and reason codes for investigation.
6. **Controlled Behavioural Adaptation:** Exploring drift monitoring and updates based on reviewed benign activities.

## 11. Future Enhancements

- Implement and evaluate the Causal Transformer branch.
- Develop HGT-based relational learning and relation prediction.
- Integrate ADWIN-based drift monitoring.
- Implement controlled behavioural baseline updates.
- Improve alert explainability and evidence presentation.
- Conduct comparative experiments using CERT benchmark datasets.
- Evaluate scalability, computational efficiency, and alert workload.
- Explore additional privacy-preserving behavioural analytics techniques.

## 12. Team Members

This project is developed by the following students of the B.Tech programme in Computer Science and Engineering (Cyber Security).

| S. No. | Team Member | Registration Number |
|---:|---|---|
| 1 | **Poreddy Rishikesh Reddy** | 2411021060340 |
| 2 | **Kanchi Srinadh** | 2411021060341 |
| 3 | **Boddapati Venkata Lakshmi Narasimha** | 2411021060415 |
| 4 | **Kommalapati Kalyan Ram** | 2411021060769 |

### Project Guide

**Dr. Neeba E A**

Alliance School of Advanced Computing  
Alliance University, Bengaluru

## 13. Academic Details

| Detail | Information |
|---|---|
| Project Title | User and Entity Behaviour Analytics (UEBA) for Internal Threat Identification |
| Project Type | Design Project – I |
| Course Code | E1CSA313 |
| Department | Computer Science and Engineering (Cyber Security) |
| Institution | Alliance School of Advanced Computing |
| University | Alliance University, Bengaluru |
| Academic Year | 2026 |

## 14. Repository

**GitHub Repository:**  
https://github.com/Rishikesh0024/Design-Project-UEBA

## 15. Acknowledgement

We express our sincere gratitude to our project guide, **Dr. Neeba E A**, for the guidance, encouragement, and valuable suggestions provided throughout the development of this project.

We also thank the faculty members and the Department of Computer Science and Engineering (Cyber Security), Alliance School of Advanced Computing, Alliance University, Bengaluru, for their support and encouragement.

---

<p align="center">
  <strong>UEBA for Internal Threat Identification</strong><br/>
  <em>Behavioural Analytics • Machine Learning • Cybersecurity • Threat Identification</em>
</p>
