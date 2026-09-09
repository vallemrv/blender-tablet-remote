# Imágenes de referencia

En la parte superior del workspace, **Referencias** abre un panel de fotos y
dibujos. Funciona en Object, Edit, CAD y Sculpt, también sin conexión a Blender.

1. Pulsa **+ Imagen** y elige una o varias imágenes de la tablet.
2. Cambia entre ellas con los botones numerados. El nombre aparece bajo la imagen.
3. Arrastra la cabecera **Referencias · mover** para colocar el panel.
4. Usa dos dedos sobre la imagen para ampliar y desplazar; **Encuadrar referencia**
   recupera la vista completa. **Ampliar/Compacta** cambia el tamaño del panel.
5. Ajusta **Opacidad** y usa **Ocultar** para recuperar espacio. **Quitar** elimina
   únicamente la copia de la referencia dentro de la aplicación.

Los gestos del panel no esculpen ni navegan la escena. Fuera del panel sigue
funcionando la superficie de entrada habitual. Las referencias son un tablero
visual de la tablet; no son planos 3D ni se guardan dentro del `.blend`.

La app conserva copias privadas para que las imágenes sigan disponibles al
reiniciarla o si se mueve el archivo original. La importación y decodificación
se ejecutan fuera del hilo de interfaz, limitan cada original a 32 MB y adaptan
el lado mayor a 2048 píxeles para acotar memoria. No se pide acceso general al
almacenamiento: se utiliza el selector de documentos de Android.

Referencia técnica: [selector de documentos de Android](https://developer.android.com/training/data-storage/shared/documents-files).
