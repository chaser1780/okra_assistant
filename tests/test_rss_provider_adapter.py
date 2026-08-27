from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from news.providers.rss import parse_rss_feed  # noqa: E402


class RssProviderAdapterTests(unittest.TestCase):
    def test_atom_href_and_html_summary_are_normalized(self):
        xml_text = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <feed xmlns=\"http://www.w3.org/2005/Atom\">
          <entry>
            <title>市场更新</title>
            <summary><![CDATA[<b>主题</b> 资讯]]></summary>
            <link href=\"https://example.test/atom/1\" />
            <updated>2026-05-20T08:30:00Z</updated>
          </entry>
        </feed>"""

        rows = parse_rss_feed(xml_text, "2026-05-20", plain_text=lambda value: value.replace("<b>", "").replace("</b>", ""))

        self.assertEqual(1, len(rows))
        self.assertEqual("https://example.test/atom/1", rows[0]["url"])
        self.assertEqual("2026-05-20T16:30:00+08:00", rows[0]["published_at"])
        self.assertEqual("主题 资讯", rows[0]["summary"])


if __name__ == "__main__":
    unittest.main()
