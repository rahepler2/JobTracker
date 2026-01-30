#!/usr/bin/env python3
"""
Initial Data Load Script for JobTracker.

This script performs the initial data load from BLS and O*NET into Typesense.
It can be run standalone or as part of the Docker deployment.

Usage:
    python -m scripts.initial_load [OPTIONS]

Options:
    --drop-existing     Drop and recreate collections before loading
    --skip-onet         Skip O*NET data (faster, BLS only)
    --skip-locations    Skip state/metro wage data
    --max-occupations   Limit number of occupations for testing
    --dry-run           Show what would be done without executing
"""

import argparse
import logging
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from src.config import get_settings
from src.pipeline import OccupationalDataPipeline
from src.typesense_loader import TypesenseLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Load BLS and O*NET data into Typesense",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Full load with all data
    python -m scripts.initial_load

    # Fresh start - drop existing collections
    python -m scripts.initial_load --drop-existing

    # Quick load for testing (BLS only, no location data)
    python -m scripts.initial_load --skip-onet --skip-locations

    # Test with limited data
    python -m scripts.initial_load --max-occupations 50 --skip-locations
        """,
    )

    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="Drop and recreate collections before loading",
    )

    parser.add_argument(
        "--skip-onet",
        action="store_true",
        help="Skip O*NET data loading (faster, BLS wages/employment only)",
    )

    parser.add_argument(
        "--skip-locations",
        action="store_true",
        help="Skip state and metro area wage data",
    )

    parser.add_argument(
        "--max-occupations",
        type=int,
        default=None,
        help="Limit number of occupations to load (for testing)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def check_prerequisites():
    """Check that required services and credentials are available."""
    settings = get_settings()
    issues = []

    # Check Typesense connection
    loader = TypesenseLoader()
    if not loader.health_check():
        issues.append(
            "Cannot connect to Typesense. "
            f"Check TYPESENSE_HOST ({settings.typesense.host}) and TYPESENSE_API_KEY"
        )

    # Check BLS API key (optional but recommended)
    if not settings.bls.api_key:
        logger.warning(
            "BLS_API_KEY not set. Using unregistered API with lower rate limits. "
            "Register at https://data.bls.gov/registrationEngine/"
        )

    # Check O*NET credentials
    if not settings.onet.username or not settings.onet.app_key:
        logger.warning(
            "O*NET credentials not set. Skills data will not be available. "
            "Register at https://services.onetcenter.org/developer/"
        )
        issues.append("O*NET credentials not configured")

    return issues


def main():
    """Run the initial data load."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("\n" + "=" * 60)
    print("JobTracker Initial Data Load")
    print("=" * 60 + "\n")

    settings = get_settings()
    print(f"Configuration:")
    print(f"  Typesense Host: {settings.typesense.host}:{settings.typesense.port}")
    print(f"  Data Year: {settings.data.year}")
    print(f"  Drop Existing: {args.drop_existing}")
    print(f"  Include O*NET: {not args.skip_onet}")
    print(f"  Include Location Wages: {not args.skip_locations}")
    if args.max_occupations:
        print(f"  Max Occupations: {args.max_occupations}")
    print()

    # Check prerequisites
    print("Checking prerequisites...")
    issues = check_prerequisites()

    if issues and not args.skip_onet:
        print("\nPrerequisite issues found:")
        for issue in issues:
            print(f"  - {issue}")

        if "Cannot connect to Typesense" in str(issues):
            print("\nCannot proceed without Typesense connection.")
            sys.exit(1)

    if args.dry_run:
        print("\n[DRY RUN] Would perform the following operations:")
        print("  1. Create/update Typesense collections")
        print("  2. Download BLS OEWS national data")
        if not args.skip_onet:
            print("  3. Fetch O*NET skills data for each occupation")
        print(f"  {'4' if not args.skip_onet else '3'}. Transform and index occupation documents")
        if not args.skip_locations:
            print("  - Download and index state wage data")
            print("  - Download and index metro area wage data")
        if not args.skip_onet:
            print("  - Build and index skills collection")
        print("\n[DRY RUN] No changes made.")
        return

    # Run the pipeline
    print("\nStarting data load...")
    start_time = datetime.now()

    try:
        pipeline = OccupationalDataPipeline()

        # If max_occupations is set, we need custom handling
        if args.max_occupations:
            logger.info(f"Limited load: max {args.max_occupations} occupations")

            # Create collections
            loader = TypesenseLoader()
            loader.create_all_collections(drop_existing=args.drop_existing)

            # Load BLS data
            from src.bls_client import BLSClient
            from src.data_transformer import DataTransformer

            bls = BLSClient()
            transformer = DataTransformer()

            national_df = bls.get_national_data()

            # Filter to detailed and limit
            if "O_GROUP" in national_df.columns:
                national_df = national_df[national_df["O_GROUP"] == "detailed"]
            national_df = national_df.head(args.max_occupations)

            # Load O*NET if enabled
            onet_data = {}
            if not args.skip_onet:
                onet_data = pipeline._load_onet_data(
                    national_df, max_occupations=args.max_occupations
                )

            # Transform and load
            docs = transformer.transform_bulk_occupations(national_df, onet_data)
            results = loader.index_documents("occupations", docs)
            print(f"Indexed {results['success']} occupations")

        else:
            # Full load
            results = pipeline.run_full_refresh(
                drop_existing=args.drop_existing,
                include_onet=not args.skip_onet,
                include_location_wages=not args.skip_locations,
            )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print("\n" + "=" * 60)
        print("Data Load Complete!")
        print("=" * 60)
        print(f"\nDuration: {duration:.2f} seconds")

        if isinstance(results, dict):
            if "occupations_indexed" in results:
                occ = results["occupations_indexed"]
                print(f"Occupations: {occ.get('success', 0)} indexed, {occ.get('failed', 0)} failed")

            if "state_wages_indexed" in results:
                state = results["state_wages_indexed"]
                print(f"State Wages: {state.get('success', 0)} indexed")

            if "metro_wages_indexed" in results:
                metro = results["metro_wages_indexed"]
                print(f"Metro Wages: {metro.get('success', 0)} indexed")

            if "skills_indexed" in results:
                skills = results["skills_indexed"]
                print(f"Skills: {skills.get('success', 0)} indexed")

        # Show collection stats
        print("\nCollection Statistics:")
        loader = TypesenseLoader()
        stats = loader.get_all_stats()
        for name, stat in stats.items():
            if isinstance(stat, dict) and "num_documents" in stat:
                print(f"  {name}: {stat['num_documents']:,} documents")

        print("\nData load completed successfully!")
        print("You can now start the API with: docker-compose up api")
        print("Or run locally with: python -m api.main")

    except KeyboardInterrupt:
        print("\n\nData load interrupted by user.")
        sys.exit(1)

    except Exception as e:
        logger.exception("Data load failed")
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
