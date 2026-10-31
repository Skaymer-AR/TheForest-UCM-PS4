using System;
using System.Collections.Generic;

namespace TheForest.UCM
{
    // Independent of Unity and the game. This is a UI-only AOT prototype.
    // Values match src/overlay.h logical button masks, NOT hardware ScePad masks.
    [Flags]
    public enum UcmButton : uint
    {
        None = 0,
        L1 = 1, R1 = 2, Up = 4, Down = 8,
        Left = 16, Right = 32, Cross = 64, Circle = 128
    }

    public enum UcmCategory
    {
        Cheats, Environment, Player, Animals, Mutants,
        Spawn, Inventory, Coop, Dev, Game, Count
    }

    public enum UcmItemKind { Toggle, Action, Slider }

    public sealed class UcmItem
    {
        public readonly string Id;
        public readonly string Label;
        public readonly UcmCategory Category;
        public readonly UcmItemKind Kind;
        public readonly bool Available;
        public readonly int Min;
        public readonly int Max;
        public readonly int Step;
        public int Value;

        public UcmItem(string id, string label, UcmCategory category, UcmItemKind kind,
                       int value, int min, int max, int step, bool available)
        {
            Id = id;
            Label = label;
            Category = category;
            Kind = kind;
            Value = value;
            Min = min;
            Max = max;
            Step = step;
            Available = available;
        }
    }

    public sealed class UcmMenuModel
    {
        private readonly UcmItem[] _items = new UcmItem[]
        {
            new UcmItem("god_mode", "God Mode", UcmCategory.Cheats, UcmItemKind.Toggle, 0, 0, 1, 1, false),
            new UcmItem("infinite_stamina", "Infinite Stamina", UcmCategory.Cheats, UcmItemKind.Toggle, 0, 0, 1, 1, false),
            new UcmItem("hunger_thirst", "Hunger and Thirst", UcmCategory.Player, UcmItemKind.Toggle, 0, 0, 1, 1, false),
            new UcmItem("free_building", "Build without materials", UcmCategory.Game, UcmItemKind.Toggle, 0, 0, 1, 1, false),
            new UcmItem("add_inventory", "Add inventory item", UcmCategory.Inventory, UcmItemKind.Action, 0, 0, 0, 0, false),
            new UcmItem("teleport", "Teleport player", UcmCategory.Player, UcmItemKind.Action, 0, 0, 0, 0, false),
            new UcmItem("spawn_enemy", "Spawn enemy", UcmCategory.Mutants, UcmItemKind.Action, 0, 0, 0, 0, false),
            new UcmItem("spawn_object", "Spawn object", UcmCategory.Spawn, UcmItemKind.Action, 0, 0, 0, 0, false),
            new UcmItem("time_of_day", "Time of day", UcmCategory.Environment, UcmItemKind.Action, 0, 0, 0, 0, false),
            new UcmItem("weather", "Weather", UcmCategory.Environment, UcmItemKind.Action, 0, 0, 0, 0, false),
            new UcmItem("hints", "Show controls", UcmCategory.Dev, UcmItemKind.Toggle, 1, 0, 1, 1, true),
            new UcmItem("opacity", "Panel opacity (opaque renderer)", UcmCategory.Dev, UcmItemKind.Slider, 100, 100, 100, 0, false),
            new UcmItem("close", "Close menu", UcmCategory.Dev, UcmItemKind.Action, 0, 0, 0, 0, true)
        };

        private readonly int[] _selection = new int[(int)UcmCategory.Count];
        private UcmButton _previous = UcmButton.None;
        private bool _inputReady;

        public bool Visible { get; private set; }
        public UcmCategory Category { get; private set; }

        public UcmItem[] Items { get { return _items; } }

        public int SelectedIndex { get { return _selection[(int)Category]; } }

        public int CountInCategory(UcmCategory category)
        {
            int count = 0;
            foreach (UcmItem entry in _items)
                if (entry.Category == category) ++count;
            return count;
        }

        public UcmItem SelectedItem()
        {
            int index = 0;
            foreach (UcmItem entry in _items)
            {
                if (entry.Category != Category) continue;
                if (index++ == SelectedIndex) return entry;
            }
            return null;
        }

        public IEnumerable<UcmItem> VisibleItems()
        {
            foreach (UcmItem entry in _items)
                if (entry.Category == Category) yield return entry;
        }

        public void Tick(bool connected, UcmButton buttons)
        {
            if (!connected)
            {
                Visible = false;
                _previous = UcmButton.None;
                _inputReady = false;
                return;
            }

            // Held inputs after startup or reconnect never trigger menu actions.
            if (!_inputReady)
            {
                if (buttons != UcmButton.None) return;
                _inputReady = true;
            }

            UcmButton pressed = buttons & ~_previous;
            UcmButton chord = UcmButton.L1 | UcmButton.R1;
            if ((buttons & chord) == chord && (_previous & chord) != chord)
            {
                Visible = !Visible;
            }
            else if (Visible)
            {
                // Deterministic priority, one action per Tick, without auto-repeat.
                if ((pressed & UcmButton.Circle) != 0) Visible = false;
                else if ((pressed & UcmButton.Up) != 0) Move(-1);
                else if ((pressed & UcmButton.Down) != 0) Move(1);
                else if ((pressed & UcmButton.Left) != 0) ChangeValue(-1);
                else if ((pressed & UcmButton.Right) != 0) ChangeValue(1);
                else if ((pressed & UcmButton.L1) != 0) ChangeCategory(-1);
                else if ((pressed & UcmButton.R1) != 0) ChangeCategory(1);
                else if ((pressed & UcmButton.Cross) != 0) Confirm();
            }
            _previous = buttons;
        }

        private void Move(int delta)
        {
            int count = CountInCategory(Category);
            if (count == 0) return;
            _selection[(int)Category] = (_selection[(int)Category] + count + delta) % count;
        }

        private void ChangeCategory(int delta)
        {
            int count = (int)UcmCategory.Count;
            Category = (UcmCategory)(((int)Category + count + delta) % count);
        }

        private void ChangeValue(int delta)
        {
            UcmItem item = SelectedItem();
            if (item == null || !item.Available || item.Kind != UcmItemKind.Slider) return;
            int value = item.Value + delta * item.Step;
            item.Value = Math.Max(item.Min, Math.Min(item.Max, value));
        }

        private void Confirm()
        {
            UcmItem item = SelectedItem();
            if (item == null || !item.Available) return;
            if (item.Id == "close")
            {
                Visible = false;
                return;
            }
            if (item.Kind == UcmItemKind.Toggle)
                item.Value = item.Value == 0 ? 1 : 0;
            // No gameplay command dispatcher: all game-mutating entries disabled.
        }
    }

    public interface IUcmInputSource
    {
        // Return false when no safe sample is available. Never consume input.
        bool TryRead(out bool connected, out UcmButton buttons);
    }

    public static class UcmInputRegistry
    {
        // Future host must bind this to *verified* Rewired action mappings.
        public static IUcmInputSource Source;
    }
}
