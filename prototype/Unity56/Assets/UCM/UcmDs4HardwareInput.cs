using System;

namespace TheForest.UCM
{
    // Rewired SonyDualShock4 *hardware element IDs* from the CUSA12398 assets.
    // These are NOT Rewired action IDs or OrbisPad/ScePad button masks.
    public static class UcmDs4ElementId
    {
        public const int Cross = 6, Circle = 7, L1 = 10, R1 = 11;
        public const int DPadUp = 18, DPadRight = 19;
        public const int DPadDown = 20, DPadLeft = 21;
    }

    // Future title-owned Unity AOT provider: an atomic snapshot of the Rewired
    // controller actually assigned to the local Player. No native PS4 API here.
    public struct UcmRewiredHardwareSnapshot
    {
        public bool Connected;
        public bool AssignedToLocalPlayer;
        public bool ControllerMapVerified;
        // Must be established by the title-owned live provider on this frame.
        // Serialized assets alone cannot verify focus or current scene ownership.
        public bool InputFocusVerified;
        public bool SceneOwnerVerified;
        public string HardwareGuid;
        // Provider-generated one-bit-per-hardware-ELEMENT mask (IDs 0..23).
        // NOT a raw ScePad bitmask or a Rewired action bitmask.
        public uint PressedElementIds;
    }

    public interface IUcmRewiredHardwareSnapshotSource
    {
        bool TryRead(out UcmRewiredHardwareSnapshot snapshot);
    }

    // Pure adapter to the existing Unity host's IUcmInputSource. This cannot
    // obtain Rewired runtime data on its own and never modifies game controls.
    public sealed class UcmDs4HardwareInput : IUcmInputSource
    {
        public const string SonyDs4GuidA = "83b427e4-086f-47f3-bb06-be266abd1ca5";
        public const string SonyDs4GuidB = "cd9718bf-a87a-44bc-8716-60a0def28a9f";
        private readonly IUcmRewiredHardwareSnapshotSource _source;

        public UcmDs4HardwareInput(IUcmRewiredHardwareSnapshotSource source)
        {
            if (source == null) throw new ArgumentNullException("source");
            _source = source;
        }

        public bool TryRead(out bool connected, out UcmButton buttons)
        {
            connected = false;
            buttons = UcmButton.None;
            UcmRewiredHardwareSnapshot snapshot;
            if (!_source.TryRead(out snapshot)) return false;
            if (!snapshot.Connected) return true;
            if (!snapshot.AssignedToLocalPlayer ||
                !snapshot.ControllerMapVerified ||
                !snapshot.InputFocusVerified ||
                !snapshot.SceneOwnerVerified ||
                !KnownHardware(snapshot.HardwareGuid) ||
                (snapshot.PressedElementIds & 0xFF000000u) != 0u) return false;

            connected = true;
            uint bits = snapshot.PressedElementIds;
            if (Has(bits, UcmDs4ElementId.L1)) buttons |= UcmButton.L1;
            if (Has(bits, UcmDs4ElementId.R1)) buttons |= UcmButton.R1;
            if (Has(bits, UcmDs4ElementId.DPadUp)) buttons |= UcmButton.Up;
            if (Has(bits, UcmDs4ElementId.DPadDown)) buttons |= UcmButton.Down;
            if (Has(bits, UcmDs4ElementId.DPadLeft)) buttons |= UcmButton.Left;
            if (Has(bits, UcmDs4ElementId.DPadRight)) buttons |= UcmButton.Right;
            if (Has(bits, UcmDs4ElementId.Cross)) buttons |= UcmButton.Cross;
            if (Has(bits, UcmDs4ElementId.Circle)) buttons |= UcmButton.Circle;
            return true;
        }

        private static bool Has(uint mask, int id)
        {
            return (mask & (1u << id)) != 0u;
        }

        private static bool KnownHardware(string guid)
        {
            return string.Equals(guid, SonyDs4GuidA, StringComparison.OrdinalIgnoreCase)
                || string.Equals(guid, SonyDs4GuidB, StringComparison.OrdinalIgnoreCase);
        }
    }
}
