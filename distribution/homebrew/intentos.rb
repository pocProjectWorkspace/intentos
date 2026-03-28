class Intentos < Formula
  desc "IntentOS — AI execution layer where language is the interface"
  homepage "https://github.com/pocProjectWorkspace/intentos"
  url "https://github.com/pocProjectWorkspace/intentos/archive/refs/tags/v2.0.0.tar.gz"
  # sha256 "will-be-computed-on-release"
  license "MIT"

  depends_on "python@3.11"
  depends_on "ollama" => :optional

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      To start IntentOS:
        intentos

      For voice input:
        pip install SpeechRecognition pyaudio

      For local AI (recommended):
        brew install ollama
        ollama pull llama3.1:8b
    EOS
  end

  test do
    system "#{bin}/intentos", "--version"
  end
end
