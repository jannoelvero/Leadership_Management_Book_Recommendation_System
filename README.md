# LeadWise --- Leadership & Management Book Intelligence

**LeadWise** is an end-to-end data analytics, natural language
processing (NLP), machine learning, recommendation, and interactive
application project focused on leadership and management books.

The project was developed as an **Ironhack Data Analytics Capstone
Project** by **Dr. Jan Noel L. Vero**. It combines book-data collection,
data cleaning and integration, relational database design, exploratory
and statistical analysis, NLP, dimensionality reduction, unsupervised
clustering, content-based recommendation, experimental neural-network
modeling, Tableau visualization, and Streamlit product development.

> **Core principle:** LeadWise uses available evidence from the catalog
> and does not fabricate unavailable book metadata. Recommendation
> similarity represents textual/content similarity, not book quality, an
> expert rating, or the probability that a reader will like a book.

------------------------------------------------------------------------

## 1. Project Overview

Leadership and management readers face a discovery problem: large book
catalogs contain overlapping topics, inconsistent metadata, incomplete
descriptions, and limited tools for identifying books relevant to a
specific leadership challenge or professional goal.

LeadWise addresses this problem by transforming heterogeneous book
records into a structured **book-intelligence system** that supports:

-   natural-language book discovery;
-   content-based recommendations;
-   similar-book exploration;
-   topic exploration;
-   side-by-side book comparison;
-   personal reading-library management;
-   reader ratings and reflections;
-   editorial Featured Reading;
-   catalog governance and administration; and
-   recommendation-processing workflows for newly added books.

The project separates **source evidence**, **machine-learning outputs**,
**reader-generated content**, and **editorial curation** so that each is
interpreted appropriately.

------------------------------------------------------------------------

## 2. Business Problem

The project investigates how data analytics and machine learning can
make leadership and management book discovery more useful and
transparent.

Key questions include:

-   How can book metadata from different sources be integrated into a
    consistent analytical catalog?
-   What leadership and management themes emerge from book content?
-   Can unsupervised learning organize books into interpretable topic
    groups?
-   Can textual features support relevant content-based recommendations?
-   How can recommendation outputs be presented without implying that
    similarity equals quality?
-   How can a research prototype evolve into an operational
    reader-facing product with catalog governance?

------------------------------------------------------------------------

## 3. Project Objectives

The capstone was designed to:

1.  Collect leadership and management book records from API and
    web-based sources.
2.  Clean, standardize, integrate, and deduplicate the collected
    records.
3.  Build a relational SQL-ready data model.
4.  Explore catalog characteristics, metadata coverage, and data
    quality.
5.  Conduct statistical analyses on selected catalog relationships.
6.  Engineer numerical, categorical, and textual features.
7.  Apply NLP to titles, authors, descriptions, categories, and related
    metadata.
8.  Apply dimensionality-reduction techniques for high-dimensional text
    features.
9.  Use unsupervised clustering to identify book-topic structures.
10. Build and evaluate a content-based recommendation engine.
11. Explore PyTorch and neural-network representations as an
    experimental extension.
12. Investigate grounded LLM integration while documenting
    implementation limitations.
13. Prepare analytical outputs for Tableau.
14. Build a Reader application and an administrative control environment
    in Streamlit.
15. Prepare the system for portable deployment.

------------------------------------------------------------------------

## 4. Data Collection

The project combines leadership and management book information
collected from multiple sources.

### Open Library

Open Library API collection produced approximately **950 unique search
records**, followed by work- and edition-level enrichment.

### LeadershipNow

LeadershipNow was used as an additional leadership/management-focused
source, producing approximately **1,124 raw records** before cleaning
and integration.

### Integrated Catalog

After cleaning, integration, and exact-overlap handling, the master
analytical catalog contains:

**2,067 book records**

The integrated catalog preserves source evidence where available rather
than filling missing values with invented information.

------------------------------------------------------------------------

## 5. Data Quality and Metadata Principles

LeadWise deliberately distinguishes between observed evidence and
inferred information.

Examples:

-   Missing descriptions are reported as unavailable rather than
    generated.
-   Missing prices are not represented as zero.
-   Publication geography is represented as **earliest observed
    publication country/countries** where supported by evidence; it is
    not automatically treated as a book's country of origin.
-   Observed publication languages are not automatically interpreted as
    verified original languages or translations.
-   Author geography is based on validated evidence rather than inferred
    from names.
-   Extreme page-count anomalies are preserved in source/audit data but
    may be suppressed from reader-facing display.
-   Source ratings are kept distinct from LeadWise community ratings and
    personal reader ratings.

The enriched application catalog contains substantially more metadata
fields than the original source tables, while preserving provenance and
auditability.

------------------------------------------------------------------------

## 6. SQL and Relational Data Architecture

The integrated data was transformed into SQL-ready relational tables
covering entities such as:

-   books;
-   authors;
-   book-author relationships;
-   editions;
-   categories;
-   book-category relationships;
-   book metrics;
-   source records; and
-   data sources.

The SQL workflow includes:

-   database creation;
-   table creation;
-   data insertion;
-   primary-key validation;
-   foreign-key validation;
-   junction-table validation; and
-   analytical queries.

The SQL scripts are available in the [`sql/`](sql/) directory.

------------------------------------------------------------------------

## 7. Exploratory Data Analysis

Exploratory analysis examines the structure and quality of the
integrated catalog, including:

-   metadata completeness;
-   source distribution;
-   publication characteristics;
-   rating availability;
-   page-count behavior;
-   category/topic information;
-   author and publisher evidence;
-   language coverage; and
-   data-quality anomalies.

EDA outputs informed subsequent feature engineering, NLP, clustering,
and recommendation design.

------------------------------------------------------------------------

## 8. Statistical Analysis

The project includes formal hypothesis testing on selected relationships
within the catalog.

Multiple hypotheses were evaluated with appropriate statistical
procedures and a **Bonferroni correction** was applied to control for
multiple comparisons.

Statistical results are interpreted from both:

-   a statistical perspective; and
-   a practical/business perspective.

The detailed analysis is documented in:

[`notebooks/07_statistical_analysis.ipynb`](notebooks/07_statistical_analysis.ipynb)

------------------------------------------------------------------------

## 9. Feature Engineering

Feature engineering converts the integrated book catalog into
machine-learning-ready representations.

The engineered feature set includes combinations of:

-   numerical metadata;
-   metadata-availability indicators;
-   categorical information;
-   publication information;
-   source information; and
-   NLP-derived text features.

A feature-engineering audit is retained so that model inputs remain
traceable to the underlying catalog.

------------------------------------------------------------------------

## 10. Natural Language Processing

LeadWise uses NLP to represent book content for topic intelligence and
recommendation.

The production text representation combines available textual evidence
such as:

-   title;
-   authors;
-   description/synopsis;
-   categories/subjects; and
-   publisher information where applicable.

The production recommendation representation uses **TF-IDF** with a
boundary-aware analyzer designed to prevent artificial n-grams from
being created across separate metadata fields.

The enriched TF-IDF representation contains approximately:

**5,130 features**

for the frozen **2,067-book** catalog.

------------------------------------------------------------------------

## 11. Dimensionality Reduction

The project investigates dimensionality reduction to better understand
high-dimensional text representations.

Techniques include:

-   Principal Component Analysis (PCA) for appropriate numerical
    features; and
-   Truncated SVD / Latent Semantic Analysis-style representations for
    sparse TF-IDF features.

Evaluation includes diagnostics such as:

-   explained variance;
-   similarity preservation;
-   neighbor preservation; and
-   component interpretation.

Dimensionality reduction supports analysis and experimentation but is
kept conceptually separate from the final production retrieval logic.

------------------------------------------------------------------------

## 12. Unsupervised Clustering

Unsupervised learning was used to identify recurring leadership and
management themes within the catalog.

Final clustering produced:

-   **29 topic clusters**
-   **1,884 clustered books**

Cluster interpretation uses features such as:

-   top terms;
-   representative books; and
-   cluster-level summaries.

Books without sufficient evidence for a defensible cluster assignment
are not forced into a topic simply for display purposes.

------------------------------------------------------------------------

## 13. Production Recommendation System

The deployed LeadWise recommendation engine is a **content-based
recommender**.

### Production approach

1.  Combine available book-content fields.
2.  Transform text using the production TF-IDF vectorizer.
3.  Represent books in the shared TF-IDF feature space.
4.  Transform a reader's natural-language query into the same space.
5.  Calculate **cosine similarity**.
6.  Rank eligible books by textual/content similarity.
7.  Suppress duplicate title-author results where appropriate.

The same representation supports **Similar Books** recommendations.

### Frozen deployment baseline

The frozen deployment contains:

-   **2,067 books**
-   **2,040 books with searchable non-zero TF-IDF vectors**
-   **27 records with zero production vectors**
-   **29 topic clusters**
-   **1,884 clustered books**

### Evaluation

The production recommendation evaluation reported approximately:

-   **97.53% recommendation coverage**
-   mean recommendation similarity: **0.322**
-   median recommendation similarity: **0.302**
-   mean rank-1 similarity: **0.513**
-   mean rank-10 similarity: **0.233**
-   mean topic diversity across evaluated recommendation sets:
    approximately **3.84 unique topics**

These metrics characterize the evaluated retrieval system. They do
**not** measure reader satisfaction or book quality.

------------------------------------------------------------------------

## 14. Dynamic Recommendation Processing

LeadWise extends the frozen capstone recommender with an operational
processing layer.

An approved, published book added through the administrative catalog can
be processed using the same production TF-IDF vectorizer. The resulting
sparse vector can be persisted and combined at runtime with the frozen
recommendation matrix.

This allows newly governed books to become recommendation-ready without
modifying the reproducible frozen base artifacts.

The system distinguishes between:

-   **Published** --- available in the reader-facing catalog;
-   **Recommendation Ready** --- has a valid searchable vector;
-   **Topic Classified** --- assigned to a topic cluster.

These are separate states.

------------------------------------------------------------------------

## 15. PyTorch and Neural-Network Experimentation

The capstone includes PyTorch-based experimentation to demonstrate a
broader machine-learning workflow.

Work includes:

-   tensor preparation;
-   sparse/dense representation handling;
-   autoencoder experimentation;
-   latent representations; and
-   model evaluation.

The neural-network work is **experimental**.

It is not presented as the production recommendation engine. The live
recommendation logic remains the more interpretable TF-IDF +
cosine-similarity approach.

------------------------------------------------------------------------

## 16. LLM Integration Investigation

LeadWise includes an investigation of potential LLM integration for
grounded book intelligence.

During development, no production OpenAI API key was available.
Consequently:

-   live external LLM inference was not made a dependency of the
    deployed system;
-   retrieval and grounding diagnostics were developed independently;
-   the production Reader remains functional without an external LLM.

The current **Ask LeadWise** experience uses deterministic FAQ/support
routing and structured workflows rather than pretending to provide
unavailable generative intelligence.

Future LLM integration should remain grounded in catalog evidence and
preserve LeadWise's no-fabrication policy.

------------------------------------------------------------------------

## 17. Tableau Analytics

Analytical datasets were prepared for Tableau to communicate findings
from:

-   catalog characteristics;
-   metadata coverage;
-   topic clusters;
-   representative books;
-   recommendation performance;
-   similarity by rank;
-   source exposure;
-   recommendation diversity;
-   dimensionality-reduction diagnostics;
-   retrieval diagnostics; and
-   experimental neural-network evaluation.

Project workbooks include:

-   `Leadership and Management.twb`
-   `Leadership and Management.twbx`

The Tableau layer is the analytical-communication component of the
capstone, while Streamlit provides the interactive product experience.

------------------------------------------------------------------------

## 18. LeadWise Reader Application

The Reader application is implemented in:

[`app/streamlit_app.py`](app/streamlit_app.py)

Current deployment-preparation baseline:

**Reader 18.57.3**

Major reader-facing areas include:

### Home

-   LeadWise visual identity and project positioning
-   catalog/recommendation KPIs
-   quick natural-language discovery
-   Featured Reading when editorial selections are available

### Discover Books

-   natural-language **For Me** retrieval
-   catalog exploration
-   content-based recommendations

### Compare Books

Side-by-side evidence comparison using available metadata.

### My Library

Registered readers can manage:

-   Want to Read;
-   Currently Reading;
-   Finished;
-   personal ratings;
-   private notes;
-   key takeaways;
-   practical-application reflections; and
-   completion dates.

### Reader Insights

Reader-generated content is separated from source metadata. Community
reviews are only surfaced through the publication workflow.

### Ask LeadWise

A support-oriented assistant provides:

-   LeadWise FAQs;
-   application guidance;
-   feedback submission;
-   general inquiries;
-   book suggestions; and
-   catalog/data-correction requests.

Book discovery remains in the dedicated Discover Books experience.

------------------------------------------------------------------------

## 19. LeadWise Administrator Control Center

LeadWise also includes a separate administrative application:

[`app/leadwise_admin_18_50_1.py`](app/leadwise_admin_18_50_1.py)

The filename is retained from the iterative development history; the
current application code contains the later portable deployment
foundation.

Administrative capabilities include:

-   operational overview;
-   usage analytics;
-   internal operations;
-   reader/user oversight;
-   Reader Insights monitoring;
-   Ask LeadWise analytics;
-   inquiry inbox;
-   book suggestions;
-   catalog management;
-   approval workflows;
-   recommendation processing;
-   Featured Reading;
-   administrative-account governance; and
-   system monitoring.

### Catalog Governance

Material catalog changes use an approval-first workflow.

Actions such as adding, editing, publishing, hiding, archiving, or
retiring records can be routed through governance requests before they
affect the effective catalog.

The design separates:

**human catalog governance** from **technical recommendation
processing**.

------------------------------------------------------------------------

## 20. Featured Reading

Featured Reading is an editorial layer, separate from machine-learning
recommendations.

Administrators can curate published books for Reader Home.

A book does not need to be Recommendation Ready simply to be editorially
featured, because:

-   **Featured Reading** = human/editorial curation;
-   **Recommended for You** = machine-learning content retrieval.

------------------------------------------------------------------------

## 21. Reader Privacy and Content Boundaries

LeadWise separates private reader information from community content.

Private reader data can include:

-   private notes;
-   key takeaways;
-   practical-application notes;
-   unpublished reflections; and
-   reading progress.

Community content is surfaced only through the appropriate publication
workflow.

Application analytics are designed not to intentionally store password
data or private journal fields as event metadata.

------------------------------------------------------------------------

## 22. Technology Stack

### Programming and analysis

-   Python
-   pandas
-   NumPy
-   SciPy
-   scikit-learn
-   PyTorch
-   Jupyter

### NLP and machine learning

-   TF-IDF
-   cosine similarity
-   PCA
-   Truncated SVD
-   clustering
-   experimental autoencoder modeling

### Data engineering

-   REST/API collection
-   web data collection
-   Selenium-based workflows
-   SQL
-   MySQL
-   relational data modeling

### Visualization and applications

-   Tableau
-   Streamlit

### Development and deployment

-   Git
-   GitHub
-   joblib
-   portable filesystem configuration
-   SQLite for the validated local/demo application state

------------------------------------------------------------------------

## 23. Repository Structure

``` text
Leadership_Management_Book_Recommendation_System/
│
├── app/
│   ├── assets/
│   │   ├── backgrounds/
│   │   └── logo/
│   ├── nlp_utils.py
│   ├── streamlit_app.py
│   ├── leadwise_admin_18_50_1.py
│   └── leadwise_promote_admin.py
│
├── data/
│   ├── raw/
│   ├── final/
│   ├── processed/
│   ├── sql_ready/
│   └── tableau/
│
├── models/
│   ├── enriched_tfidf_matrix.npz
│   ├── enriched_tfidf_vectorizer_streamlit.joblib
│   └── experimental/supporting model artifacts
│
├── notebooks/
│   ├── 00_business_understanding.ipynb
│   ├── 01_api_collection.ipynb
│   ├── 02_web_scraping.ipynb
│   ├── 03_data_cleaning.ipynb
│   ├── 04_data_integration.ipynb
│   ├── 05_sql_analysis.ipynb
│   ├── 06_exploratory_data_analysis.ipynb
│   ├── 07_statistical_analysis.ipynb
│   ├── 08_feature_engineering.ipynb
│   ├── 09_nlp_analysis.ipynb
│   ├── 10_pca.ipynb
│   ├── 11_clustering.ipynb
│   ├── 12_recommendation_system.ipynb
│   ├── 13_pytorch_tensors.ipynb
│   ├── 14_simple_neural_network.ipynb
│   ├── 15_llm_recommendation.ipynb
│   ├── 16_model_evaluation.ipynb
│   ├── 17_tableau_preparation.ipynb
│   └── 18_streamlit_application_development.ipynb
│
├── sql/
│   ├── 01_create_database.sql
│   ├── 02_create_tables.sql
│   ├── 03_insert_data.sql
│   ├── 04_data_validation.sql
│   └── 05_analysis_queries.sql
│
├── Leadership and Management.twb
├── Leadership and Management.twbx
├── requirements.txt
├── .gitignore
└── README.md
```

------------------------------------------------------------------------

## 24. Notebook Workflow

The project is documented sequentially:

  Notebook   Stage
  ---------- ------------------------------------------------
  `00`       Business Understanding
  `01`       API Collection
  `02`       Web Scraping / Web Data Collection
  `03`       Data Cleaning
  `04`       Data Integration
  `05`       SQL Analysis
  `06`       Exploratory Data Analysis
  `07`       Statistical Analysis
  `08`       Feature Engineering
  `09`       NLP Analysis
  `10`       PCA / Dimensionality Reduction
  `11`       Clustering
  `12`       Recommendation System
  `13`       PyTorch Tensors
  `14`       Simple Neural Network / Autoencoder Experiment
  `15`       LLM Recommendation Investigation
  `16`       Model Evaluation
  `17`       Tableau Preparation
  `18`       Streamlit Application Development

------------------------------------------------------------------------

## 25. Local Installation

Clone the repository:

``` bash
git clone https://github.com/jannoelvero/Leadership_Management_Book_Recommendation_System.git
cd Leadership_Management_Book_Recommendation_System
```

Create and activate a virtual environment using your preferred Python
environment manager.

Install the deployment dependencies:

``` bash
pip install -r requirements.txt
```

------------------------------------------------------------------------

## 26. Run the Reader

From the project root:

``` bash
streamlit run app/streamlit_app.py
```

The application uses portable project-relative paths for its catalog,
models, and visual assets.

For local/demo reader state, SQLite is used by default.

An alternate writable SQLite path can be supplied with the
`LEADWISE_SQLITE_PATH` environment variable.

Example:

``` bash
LEADWISE_SQLITE_PATH=/tmp/leadwise_test.db streamlit run app/streamlit_app.py
```

------------------------------------------------------------------------

## 27. Run the Administrator Control Center

From the `app/` directory, the current administrative application can be
launched with:

``` bash
streamlit run leadwise_admin_18_50_1.py --server.port 8502
```

Administrative access depends on the configured local application
database and appropriate user role.

**Do not commit production credentials, secrets, or local application
databases to the repository.**

------------------------------------------------------------------------

## 28. Deployment Architecture

The current deployment foundation is designed so that the reproducible
analytical artifacts remain separate from mutable reader/application
state.

### Version-controlled

Examples include:

-   frozen deployment catalog;
-   production TF-IDF matrix;
-   production TF-IDF vectorizer;
-   application source;
-   NLP utilities;
-   visual assets;
-   notebooks;
-   SQL;
-   Tableau workbooks.

### Not version-controlled

Examples include:

-   local SQLite application databases;
-   passwords or secrets;
-   virtual environments;
-   environment files;
-   runtime caches; and
-   local user-generated state.

The first public Reader deployment can operate using the frozen catalog
and production recommendation artifacts without requiring the
developer's local database.

------------------------------------------------------------------------

## 29. Deployment Limitation: SQLite Persistence

SQLite is suitable for the validated local application and
portfolio/demo deployment, but cloud-hosted ephemeral filesystems should
**not** be treated as durable shared production storage.

Therefore, cloud-created accounts, library activity, feedback, or other
mutable state may not be durable across restarts/redeployments when the
application is hosted on an ephemeral filesystem.

A future production architecture should use a shared persistent database
such as PostgreSQL.

The application already separates the frozen analytical layer from the
mutable operational layer to support that migration.

------------------------------------------------------------------------

## 30. Key Validated Results

  Measure                                        Result
  ------------------------------------- ---------------
  Integrated book catalog                         2,067
  Production TF-IDF features                      5,130
  Searchable frozen vectors                       2,040
  Zero-vector frozen records                         27
  Topic clusters                                     29
  Clustered books                                 1,884
  Recommendation coverage                        97.53%
  Mean recommendation similarity                  0.322
  Median recommendation similarity                0.302
  Mean rank-1 similarity                          0.513
  Mean rank-10 similarity                         0.233
  Mean recommendation topic diversity     \~3.84 topics

------------------------------------------------------------------------

## 31. Interpretation of Recommendation Scores

A LeadWise similarity score answers:

> **How similar is the available textual/content evidence for this
> result to the query or reference book in the production TF-IDF feature
> space?**

It does **not** mean:

-   the book is objectively better;
-   the reader has a particular probability of liking it;
-   the book has been endorsed by an expert;
-   the result is a quality ranking; or
-   a high-similarity book should automatically be preferred over a
    lower-similarity book.

This distinction is central to responsible interpretation of the
recommender.

------------------------------------------------------------------------

## 32. Limitations

Important limitations include:

-   many source records have incomplete metadata;
-   only a subset of books contain usable descriptions;
-   ratings are sparsely available and source-dependent;
-   verified commercial price data is not available across the catalog;
-   publication geography is evidence-based but incomplete;
-   observed languages do not establish original language or verified
    translation history;
-   clustering is an analytical representation rather than a definitive
    taxonomy;
-   content-based recommendation can favor lexical/semantic similarity
    and does not directly learn individual preference;
-   the current Reader does not use a live external LLM;
-   SQLite cloud state should not be treated as durable production
    persistence; and
-   newly processed books can become recommendation-ready without
    automatically receiving a topic-cluster assignment.

------------------------------------------------------------------------

## 33. Future Development

Potential future development includes:

-   persistent PostgreSQL/Supabase operational storage;
-   shared Reader/Admin cloud state;
-   stronger authentication and production security controls;
-   richer verified book metadata;
-   additional source and bibliographic enrichment;
-   recommendation feedback loops;
-   hybrid recommendation approaches;
-   cluster assignment for newly processed books;
-   stronger evaluation using real reader interactions;
-   grounded LLM assistance using retrieved LeadWise evidence;
-   enhanced mobile/PWA behavior; and
-   production monitoring and observability.

------------------------------------------------------------------------

## 34. Reproducibility

The project intentionally preserves the distinction between:

1.  **frozen capstone artifacts** used for reproducible analysis and
    evaluation;
2.  **experimental model artifacts** used for research;
3.  **dynamic catalog records** introduced through administrative
    workflows; and
4.  **reader-generated operational data** created during application
    use.

This architecture allows the original capstone results to remain
reproducible while supporting product experimentation.

------------------------------------------------------------------------

## 35. Author

**Dr. Jan Noel L. Vero**

Hospitality & Tourism Management · Higher Education · Business & Data
Analytics · Program & Partnership Management

-   GitHub: https://github.com/jannoelvero
-   Kaggle: https://www.kaggle.com/jannoelvero

------------------------------------------------------------------------

## 36. Project Repository

**GitHub Repository**

https://github.com/jannoelvero/Leadership_Management_Book_Recommendation_System

------------------------------------------------------------------------

## 37. Project Status

**Capstone analytical workflow:** Complete\
**Tableau analytical layer:** Complete\
**LeadWise Reader:** Deployment preparation complete\
**LeadWise Admin Control Center:** Local operational prototype complete\
**Public Reader deployment:** In progress

------------------------------------------------------------------------

### LeadWise

**Leadership & Management Book Intelligence**

*Discover the right ideas for the leader you want to become.*
