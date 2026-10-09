$source = @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public class DsProbe {
    [ComImport, Guid("62BE5D10-60EB-11d0-BD3B-00A0C911CE86")]
    public class CreateDevEnum {}

    [ComImport, Guid("29840822-5B84-11D0-BD3B-00A0C911CE86"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface ICreateDevEnum {
        [PreserveSig]
        int CreateClassEnumerator([In, MarshalAs(UnmanagedType.LPStruct)] Guid pType, out IEnumMoniker ppEnumMoniker, [In] int dwFlags);
    }

    [ComImport, Guid("55272A00-42CB-11CE-8135-00AA004BB851"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPropertyBag {
        [PreserveSig]
        int Read([In, MarshalAs(UnmanagedType.LPWStr)] string pszPropName, [In, Out, MarshalAs(UnmanagedType.Struct)] ref object pVar, [In] IntPtr pErrorLog);
        [PreserveSig]
        int Write([In, MarshalAs(UnmanagedType.LPWStr)] string pszPropName, [In, MarshalAs(UnmanagedType.Struct)] ref object pVar);
    }

    public static void ListVideoDevices() {
        Guid CLSID_VideoInputDeviceCategory = new Guid("860BB310-5D01-11d0-BD3B-00A0C911CE86");
        Guid IID_IPropertyBag = new Guid("55272A00-42CB-11CE-8135-00AA004BB851");

        ICreateDevEnum devEnum = (ICreateDevEnum)new CreateDevEnum();
        IEnumMoniker enumMoniker;
        int hr = devEnum.CreateClassEnumerator(CLSID_VideoInputDeviceCategory, out enumMoniker, 0);
        if (hr != 0 || enumMoniker == null) {
            return;
        }

        IMoniker[] monikers = new IMoniker[1];
        IntPtr fetched = IntPtr.Zero;
        int idx = 0;
        while (enumMoniker.Next(1, monikers, fetched) == 0) {
            object bagObj;
            monikers[0].BindToStorage(null, null, ref IID_IPropertyBag, out bagObj);
            IPropertyBag propBag = (IPropertyBag)bagObj;
            object val = null;
            propBag.Read("FriendlyName", ref val, IntPtr.Zero);
            object devPath = null;
            propBag.Read("DevicePath", ref devPath, IntPtr.Zero);
            string name = val != null ? val.ToString() : "Unknown";
            string path = devPath != null ? devPath.ToString() : "";
            Console.WriteLine(idx + "::" + name + "::" + path);
            Marshal.ReleaseComObject(monikers[0]);
            idx++;
        }
    }
}
'@

Add-Type -TypeDefinition $source
[DsProbe]::ListVideoDevices()
