using System.Buffers.Binary;
using System.Security.Cryptography;
using AssetsTools.NET;
using AssetsTools.NET.Extra;

// Independent container check. Class database covers MonoBehaviour built-ins,
// not PlayMakerFSM's private schema or the unknown forty-byte tail.
internal static class PlayMakerFormat17Probe
{
    public const string OriginalName = "Synthetic PlayMaker Menu (not importable)";
    public const string RewrittenName = "Synthetic PlayMaker Menu (AssetsTools.NET rewrite)";
    private const string SceneFile = "synthetic_playmaker_scene.assets";
    private const string LibraryFile = "synthetic_playmaker_library.assets";

    public static string Validate(string classData, string root, string expectedName)
    {
        var manager = NewManager(classData);
        AssetsFileInstance library = manager.LoadAssetsFile(Path.Combine(root, LibraryFile));
        AssetsFileInstance scene = manager.LoadAssetsFile(Path.Combine(root, SceneFile));
        if (scene.file.Header.Version != 17 || library.file.Header.Version != 17 ||
            scene.file.Metadata.UnityVersion != "5.6.6f2" ||
            library.file.Metadata.UnityVersion != "5.6.6f2" ||
            scene.file.Metadata.TypeTreeEnabled || library.file.Metadata.TypeTreeEnabled)
            throw new InvalidDataException("PlayMaker fixture Unity format/version/TypeTree mismatch");
        if (scene.file.Metadata.AssetInfos.Count != 3 ||
            library.file.Metadata.AssetInfos.Count != 1)
            throw new InvalidDataException("PlayMaker fixture object count mismatch");

        var goInfo = Find(scene.file, 1, 100);
        var transformInfo = Find(scene.file, 4, 200);
        var monoInfo = Find(scene.file, 114, 300);
        var scriptInfo = Find(library.file, 115, 900);
        var goField = manager.GetBaseField(scene, goInfo);
        if (goField["m_Name"].AsString != expectedName)
            throw new InvalidDataException("PlayMaker fixture GameObject name mismatch");
        var components = goField["m_Component.Array"].Children;
        if (components.Count != 2 ||
            components[0]["component.m_PathID"].AsLong != 200 ||
            components[1]["component.m_PathID"].AsLong != 300)
            throw new InvalidDataException("PlayMaker fixture component PPtrs mismatch");
        var transform = manager.GetBaseField(scene, transformInfo);
        if (transform["m_GameObject.m_PathID"].AsLong != 100)
            throw new InvalidDataException("PlayMaker fixture Transform owner mismatch");

        var mono = manager.GetBaseField(scene, monoInfo);
        if (mono["m_GameObject.m_PathID"].AsLong != 100 ||
            !mono["m_Enabled"].AsBool ||
            mono["m_Script.m_FileID"].AsInt != 1 ||
            mono["m_Script.m_PathID"].AsLong != 900)
            throw new InvalidDataException("PlayMaker MonoBehaviour base mismatch");
        if (scene.file.Metadata.ScriptTypes.Count != 1 ||
            scene.file.Metadata.ScriptTypes[0].FileId != 1 ||
            scene.file.Metadata.ScriptTypes[0].PathId != 900 ||
            scene.file.Metadata.Externals.Count != 1 ||
            Path.GetFileName(scene.file.Metadata.Externals[0].PathName) != LibraryFile ||
            monoInfo.GetScriptIndex(scene.file) != 0)
            throw new InvalidDataException("PlayMaker fixture script table/dependency mismatch");
        var dep = scene.GetDependency(manager, 0);
        if (dep == null || !ReferenceEquals(dep.file, library.file))
            throw new InvalidDataException("PlayMaker fixture dependency resolution failed");
        var script = manager.GetBaseField(dep, scriptInfo);
        if (script["m_ClassName"].AsString != "PlayMakerFSM" ||
            script["m_Namespace"].AsString != "" ||
            script["m_AssemblyName"].AsString != "SyntheticOnly.dll" ||
            script["m_IsEditorScript"].AsBool)
            throw new InvalidDataException("PlayMaker fixture MonoScript identity mismatch");

        byte[] fileBytes = File.ReadAllBytes(Path.Combine(root, SceneFile));
        int begin = checked((int)monoInfo.GetAbsoluteByteOffset(scene.file));
        int size = checked((int)monoInfo.ByteSize);
        if (size < 1000 || size > 4096 || begin < 0 || begin > fileBytes.Length - size)
            throw new InvalidDataException("PlayMaker fixture raw component bounds invalid");
        ReadOnlySpan<byte> raw = fileBytes.AsSpan(begin, size);
        if (BinaryPrimitives.ReadInt32LittleEndian(raw.Slice(0, 4)) != 0 ||
            BinaryPrimitives.ReadInt64LittleEndian(raw.Slice(4, 8)) != 100 ||
            raw[12] != 1 ||
            BinaryPrimitives.ReadInt32LittleEndian(raw.Slice(16, 4)) != 1 ||
            BinaryPrimitives.ReadInt64LittleEndian(raw.Slice(20, 8)) != 900)
            throw new InvalidDataException("PlayMaker raw MonoBehaviour header invalid");
        if (!raw.Slice(32, 12).SequenceEqual(new byte[12]) ||
            !raw.Slice(size - 12, 12).SequenceEqual(new byte[12]))
            throw new InvalidDataException("PlayMaker fixture null serialized PPtrs changed");
        string sha = Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant();
        manager.UnloadAll();
        return sha;
    }

    public static void Rewrite(string classData, string root, string outputRoot)
    {
        var manager = NewManager(classData);
        AssetsFileInstance library = manager.LoadAssetsFile(Path.Combine(root, LibraryFile));
        AssetsFileInstance scene = manager.LoadAssetsFile(Path.Combine(root, SceneFile));
        var goInfo = Find(scene.file, 1, 100);
        var go = manager.GetBaseField(scene, goInfo);
        go["m_Name"].AsString = RewrittenName;
        goInfo.SetNewData(go);
        using (var writer = new AssetsFileWriter(Path.Combine(outputRoot, LibraryFile)))
            library.file.Write(writer);
        using (var writer = new AssetsFileWriter(Path.Combine(outputRoot, SceneFile)))
            scene.file.Write(writer);
        manager.UnloadAll();
    }

    private static AssetsManager NewManager(string classData)
    {
        var manager = new AssetsManager();
        manager.LoadClassPackage(classData);
        manager.LoadClassDatabaseFromPackage("5.6.6f2");
        return manager;
    }

    private static AssetFileInfo Find(AssetsFile file, int classId, long pathId)
    {
        return file.Metadata.AssetInfos.Single(item =>
            item.TypeId == classId && item.PathId == pathId);
    }
}
