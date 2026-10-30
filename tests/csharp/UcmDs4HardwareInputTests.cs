using System;
using TheForest.UCM;

public sealed class MockDs4Input : IUcmRewiredHardwareSnapshotSource
{
    public bool Available = true;
    public UcmRewiredHardwareSnapshot Snapshot;
    public bool TryRead(out UcmRewiredHardwareSnapshot snapshot)
    {
        snapshot = Snapshot;
        return Available;
    }
}

public static class UcmDs4HardwareInputTests
{
    private static int assertions;
    private static void Check(bool condition, string name)
    {
        assertions++;
        if (!condition) throw new Exception("DS4 input test failed: " + name);
    }

    public static void Main()
    {
        MockDs4Input source = new MockDs4Input();
        UcmDs4HardwareInput input = new UcmDs4HardwareInput(source);
        bool connected;
        UcmButton buttons;
        source.Snapshot = new UcmRewiredHardwareSnapshot {
            Connected = true, AssignedToLocalPlayer = true,
            ControllerMapVerified = true,
            InputFocusVerified = true, SceneOwnerVerified = true,
            HardwareGuid = UcmDs4HardwareInput.SonyDs4GuidA,
            PressedElementIds = (1u << UcmDs4ElementId.L1) |
                                (1u << UcmDs4ElementId.R1) |
                                (1u << UcmDs4ElementId.Cross)
        };
        Check(input.TryRead(out connected, out buttons), "verified frame accepted");
        Check(connected, "controller connected");
        Check(buttons == (UcmButton.L1 | UcmButton.R1 | UcmButton.Cross),
              "physical element IDs normalized correctly");
        source.Snapshot.HardwareGuid = UcmDs4HardwareInput.SonyDs4GuidB.ToUpperInvariant();
        Check(input.TryRead(out connected, out buttons), "second known GUID accepted");
        source.Snapshot.HardwareGuid = "00000000-0000-0000-0000-000000000000";
        Check(!input.TryRead(out connected, out buttons), "unknown device rejected");
        Check(!connected && buttons == UcmButton.None, "unknown device gives neutral frame");
        source.Snapshot.HardwareGuid = UcmDs4HardwareInput.SonyDs4GuidA;
        source.Snapshot.AssignedToLocalPlayer = false;
        Check(!input.TryRead(out connected, out buttons), "unassigned controller rejected");
        source.Snapshot.AssignedToLocalPlayer = true;
        source.Snapshot.ControllerMapVerified = false;
        Check(!input.TryRead(out connected, out buttons), "unverified controller map rejected");
        source.Snapshot.ControllerMapVerified = true;
        source.Snapshot.InputFocusVerified = false;
        Check(!input.TryRead(out connected, out buttons), "unverified live focus rejected");
        Check(!connected && buttons == UcmButton.None, "lost focus gives neutral frame");
        source.Snapshot.InputFocusVerified = true;
        source.Snapshot.SceneOwnerVerified = false;
        Check(!input.TryRead(out connected, out buttons), "unverified scene owner rejected");
        Check(!connected && buttons == UcmButton.None, "lost scene gives neutral frame");
        source.Snapshot.SceneOwnerVerified = true;
        source.Snapshot.PressedElementIds |= (1u << 27);
        Check(!input.TryRead(out connected, out buttons), "unknown hardware element rejected");
        Check(!connected && buttons == UcmButton.None, "invalid element gives neutral frame");
        source.Snapshot.PressedElementIds &= ~(1u << 27);
        Check(input.TryRead(out connected, out buttons), "valid hardware snapshot recovers");
        Check(connected && (buttons & UcmButton.Cross) != 0, "valid recovered buttons normalized");
        source.Snapshot.Connected = false;
        Check(input.TryRead(out connected, out buttons), "disconnection can be reported");
        Check(!connected && buttons == UcmButton.None, "disconnection is neutral");
        source.Available = false;
        Check(!input.TryRead(out connected, out buttons), "failed provider read rejected");
        Check(!connected && buttons == UcmButton.None, "provider failure stays neutral");
        Console.WriteLine("UcmDs4HardwareInputTests: PASS (" + assertions + " assertions)");
    }
}
