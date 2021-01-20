import os
import requests
from bs4 import BeautifulSoup
from policy_sentry.querying.all import get_all_service_prefixes
from policy_sentry.shared.iam_data import get_service_prefix_data
# from aws_allowlister.database.scraping_data import ScrapingData, add_scraping_entry_to_input_database
from aws_allowlister.database.raw_scraping_data import RawScrapingData
from aws_allowlister.database.transformed_scraping_data import TransformedScrapingData
from aws_allowlister.scrapers.aws_docs import get_aws_html
from aws_allowlister.shared.utils import clean_service_name

ALL_SERVICE_PREFIXES = get_all_service_prefixes()


def scrape_hipaa_table(db_session):
    html_docs_destination = os.path.join(
        os.path.dirname(__file__), os.path.pardir, os.path.pardir, "data"
    )
    file_name = "hipaa-eligible-services-reference.html"
    html_file_path = os.path.join(html_docs_destination, file_name)
    if os.path.exists(html_file_path):
        os.remove(html_file_path)
    link = "https://aws.amazon.com/compliance/hipaa-eligible-services-reference/"

    get_aws_html(link, html_docs_destination, file_name)
    response = requests.get(link, allow_redirects=False)
    soup = BeautifulSoup(response.content, "html.parser")
    raw_scraping_data = RawScrapingData()

    service_names = []

    # These show up as list items but are not relevant at all
    false_positives = [
        "AWS Cloud Security",
        "AWS Solutions Portfolio",
        "AWS Partner Network",
        "AWS Careers",
        "AWS Support Overview",
    ]
    with open(os.path.join(html_docs_destination, file_name), "r") as f:
        soup = BeautifulSoup(response.content, "html.parser")
        for tag in soup.find_all("li"):
            if tag.text.startswith("Amazon") or tag.text.startswith("AWS"):
                if tag.text not in false_positives:
                    service_names.append(tag.text)
    for service_name in service_names:
        raw_scraping_data.add_entry_to_database(
            db_session=db_session,
            compliance_standard_name="HIPAA",
            sdk="",  # The HIPAA table does not list SDKs. We will update it to match in a second.
            service_name=clean_service_name(service_name),
        )
    transform_database_by_matching_hipaa_names_with_iam_names(db_session)


def transform_database_by_matching_hipaa_names_with_iam_names(db_session):
    transformed_scraping_data = TransformedScrapingData()
    standard = "HIPAA"
    # The service name in IAM-land
    iam_service_names = {}
    for service_prefix in ALL_SERVICE_PREFIXES:
        iam_service_names[service_prefix] = get_service_prefix_data(service_prefix)[
            "service_name"
        ]

    # The service name in compliance land
    compliance_service_names = (
        transformed_scraping_data.get_service_names_matching_compliance_standard(
            db_session, standard
        )
    )
    for iam_service_prefix in list(iam_service_names.keys()):
        iam_name = iam_service_names[iam_service_prefix]
        compliance_names = list(compliance_service_names.keys())
        for name in compliance_names:
            if iam_name.lower() == name.lower():
                transformed_scraping_data.set_sdk_name_given_service_name(
                    db_session=db_session,
                    service_name=iam_name,
                    sdk_name=iam_service_prefix,
                )
