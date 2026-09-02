import asyncio
import random
from dataclasses import dataclass


@dataclass
class FakeReport:
    reporter: str
    proxy: str
    reason: str


class MockModerationSystem:
    def __init__(self):
        self.reports = []
        self.account_status = "ACTIVE"

    async def receive_report(self, report: FakeReport):
        # محاكاة زمن معالجة السيرفر
        await asyncio.sleep(random.uniform(0.01, 0.08))

        self.reports.append(report)

        # قاعدة آلية وهمية للمختبر
        if len(self.reports) >= 100:
            self.account_status = "UNDER_REVIEW"

        if len(self.reports) >= 250:
            self.account_status = "SUSPENDED"


async def fake_reporter(
    moderation: MockModerationSystem,
    reporter_id: int,
):
    report = FakeReport(
        reporter=f"FAKE-REPORTER-{reporter_id:04d}",
        proxy=f"SIMULATED-PROXY-{random.randint(1, 500):03d}",
        reason=random.choice([
            "impersonation",
            "spam",
            "harassment",
        ]),
    )

    await moderation.receive_report(report)


async def run_simulation(total_reports=500):
    moderation = MockModerationSystem()

    tasks = [
        fake_reporter(moderation, i)
        for i in range(1, total_reports + 1)
    ]

    await asyncio.gather(*tasks)

    return moderation


async def main():
    result = await run_simulation(500)

    print("=== MASS REPORTING LAB ===")
    print(f"Reports: {len(result.reports)}")
    print(f"Account status: {result.account_status}")


if __name__ == "__main__":
    asyncio.run(main())