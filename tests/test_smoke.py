from computer_use_automation_system import main


def test_main_smoke(capsys) -> None:
    main()
    captured = capsys.readouterr()
    assert "computer-use-automation-system" in captured.out
