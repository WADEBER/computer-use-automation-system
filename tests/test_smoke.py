from computer_use_automation_system import main


def test_main_smoke(capsys) -> None:
    code = main([])
    captured = capsys.readouterr()
    assert code == 0
    assert "computer-use-automation-system" in captured.out
    assert "discover" in captured.out
    assert "replay" in captured.out
