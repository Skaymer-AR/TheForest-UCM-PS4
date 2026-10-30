using System;
using TheForest.UCM;

public static class UcmMenuModelTests
{
    private static int _assertions;
    private static void Assert(bool condition, string description)
    {
        _assertions++;
        if (!condition) throw new Exception("Assertion failed: " + description);
    }

    private static void Tap(UcmMenuModel model, UcmButton button)
    {
        model.Tick(true, UcmButton.None);
        model.Tick(true, button);
        model.Tick(true, UcmButton.None);
    }

    public static void Main()
    {
        UcmMenuModel model = new UcmMenuModel();
        Assert(model.Items.Length == 13, "13 menu entries align with src/overlay.c");
        Assert(model.Category == UcmCategory.Cheats, "starting category");
        Assert(!model.Visible, "hidden initially");
        Assert(model.CountInCategory(UcmCategory.Cheats) == 2, "cheat category count");
        Assert(model.CountInCategory(UcmCategory.Dev) == 3, "dev category count");
        Assert(model.CountInCategory(UcmCategory.Animals) == 0, "empty category supported");

        UcmButton chord = UcmButton.L1 | UcmButton.R1;
        model.Tick(true, chord);
        Assert(!model.Visible, "held chord ignored before neutral sample");
        model.Tick(true, UcmButton.None);
        Tap(model, chord);
        Assert(model.Visible, "L1+R1 opens menu");

        UcmItem first = model.SelectedItem();
        Assert(first != null && first.Id == "god_mode", "god mode initially selected");
        Tap(model, UcmButton.Cross);
        Assert(first.Value == 0, "game-changing toggle remains locked");

        Tap(model, UcmButton.Down);
        Assert(model.SelectedIndex == 1, "D-pad down selects next item");
        Tap(model, UcmButton.Down);
        Assert(model.SelectedIndex == 0, "D-pad wraps within category");
        model.Tick(true, UcmButton.Down);
        model.Tick(true, UcmButton.Down);
        Assert(model.SelectedIndex == 1, "held input does not repeat");
        model.Tick(true, UcmButton.None);

        Tap(model, UcmButton.L1);
        Assert(model.Category == UcmCategory.Game, "L1 wraps to Game");
        Tap(model, UcmButton.L1);
        Assert(model.Category == UcmCategory.Dev, "L1 reaches Dev");
        UcmItem hints = model.SelectedItem();
        Assert(hints != null && hints.Id == "hints", "Dev hints item");
        Assert(hints.Value == 1, "hints starts on");
        Tap(model, UcmButton.Cross);
        Assert(hints.Value == 0, "prototype-only hints toggle is allowed");

        Tap(model, UcmButton.Down);
        UcmItem opacity = model.SelectedItem();
        Tap(model, UcmButton.Right);
        Assert(opacity.Value == 100, "opacity locked pending renderer support");
        Tap(model, UcmButton.Down);
        Assert(model.SelectedItem().Id == "close", "select close");
        Tap(model, UcmButton.Cross);
        Assert(!model.Visible, "close entry closes menu");

        Tap(model, chord);
        Assert(model.Visible, "can reopen");
        model.Tick(false, UcmButton.None);
        Assert(!model.Visible, "disconnect closes menu");
        model.Tick(true, chord);
        Assert(!model.Visible, "reconnect with held chord ignored");
        model.Tick(true, UcmButton.None);
        Tap(model, chord);
        Assert(model.Visible, "neutral sample re-arms input after reconnect");
        Tap(model, UcmButton.Circle);
        Assert(!model.Visible, "circle closes menu");

        Console.WriteLine("UcmMenuModelTests: PASS (" + _assertions + " assertions)");
    }
}
