# Homebrew Cask for Ephe (R20 — distribution parity).
#
# Usage (official tap):
#   brew tap bemlerlabs/tap
#   brew install --cask bemlerlabs/tap/ephe
#
# The tap copy is written by scripts/render_packaging.py at release time, which fills the
# version and the sha256 from the published release. This file is the template it reads, so
# keep its shape; the numbers are checked against the release by scripts/packaging_freshness.py.
cask "ephe" do
  version "0.1.0-beta.4"
  license "BUSL-1.1"
  sha256 "92f805eadc11cb4e28ca66af2698341621a11c1c430a72f29c518e569f9d8cda" # measured from the published DMG

  url "https://github.com/bemlerlabs/ephe/releases/download/v#{version}/Ephe_#{version}_aarch64.dmg"
  name "Ephe"
  desc "Local-first AI assistant — private, offline, yours"
  homepage "https://github.com/bemlerlabs/ephe"

  app "Ephe.app"

  zap trash: [
    "~/.ephe",
    "~/Library/Application Support/com.ephe.ephe",
  ]
end
